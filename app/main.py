import csv
import io
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.answer import answer_question
from app.chunking import chunk_pages
from app.config import settings
from app.db import close_pool, init_db, load_flooring, save_document, save_flooring
from app.embeddings import embed_texts, get_model
from app.extractor import extract_flooring
from app.llm import LLMUnavailableError
from app.pdf_utils import InvalidPDFError, extract_pages
from app.retrieval import document_exists, get_all_chunks, get_document
from app.schemas import (
    AskRequest,
    AskResponse,
    DocumentInfo,
    DocumentUploadResponse,
    FlooringSchedule,
)
from app.search import search


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: create tables, load the embedding model.
    init_db()
    get_model()
    yield
    # Runs when the server stops.
    close_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS: browsers block a page on one site (e.g. localhost:3000, the frontend) from
# calling an API on another (localhost:8000) unless the API says that site is allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def hello():
    return {"message": "Hello from PlanChat"}


# Simple health check, used later by Docker / Render to see if the app is alive.
@app.get("/health")
def health():
    return {"status": "ok"}


# A normal `def` (not `async def`): PDF parsing and embedding are slow CPU work, and
# FastAPI runs `def` endpoints in a thread pool so one big upload doesn't freeze the server.
@app.post("/documents", response_model=DocumentUploadResponse)
def upload_document(file: UploadFile):
    max_bytes = settings.max_upload_mb * 1024 * 1024
    # Read one byte past the limit, so we know if the file is too big
    # without loading a huge file fully into memory.
    pdf_bytes = file.file.read(max_bytes + 1)

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB"
        )
    # Check the real content, not the filename: every PDF starts with "%PDF".
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="File is not a PDF")

    try:
        pages = extract_pages(pdf_bytes)
    except InvalidPDFError:
        raise HTTPException(status_code=400, detail="PDF is damaged or unreadable")

    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    embeddings = embed_texts([c["text"] for c in chunks])

    # A random ID so two "plans.pdf" uploads never clash, and a strange filename
    # can't write outside the uploads folder.
    document_id = uuid.uuid4()
    filename = file.filename or "upload.pdf"
    save_document(document_id, filename, len(pages), chunks, embeddings)

    # Save the file only after the database save worked.
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{document_id}.pdf").write_bytes(pdf_bytes)

    return DocumentUploadResponse(
        document_id=str(document_id),
        filename=filename,
        page_count=len(pages),
        chunk_count=len(chunks),
        pages_without_text=[p["page_number"] for p in pages if not p["text"]],
    )


@app.get("/documents/{document_id}", response_model=DocumentInfo)
def read_document(document_id: uuid.UUID):
    document = get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not document_exists(request.document_id):
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Hybrid search: chunks closest in meaning + chunks with the exact codes.
    chunks, hint = search(request.document_id, request.question)

    # 2. Ask the LLM to answer from those chunks only, with page citations.
    try:
        result = answer_question(request.question, chunks, hint)
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=error.message)

    return AskResponse(**result)


def _require_document(document_id: uuid.UUID) -> dict:
    document = get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


# POST because it does work (LLM calls) and may take a minute or two on big plan sets.
@app.post("/documents/{document_id}/flooring", response_model=FlooringSchedule)
def extract_flooring_schedule(document_id: uuid.UUID):
    _require_document(document_id)
    try:
        result = extract_flooring(get_all_chunks(document_id))
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=error.message)
    save_flooring(document_id, result["items"])
    extracted_at, items = load_flooring(document_id)
    return FlooringSchedule(
        document_id=str(document_id),
        extracted_at=extracted_at,
        items=items,
        warnings=result["warnings"],
    )


# GET returns the saved schedule: free and instant, no LLM call.
@app.get("/documents/{document_id}/flooring", response_model=FlooringSchedule)
def read_flooring_schedule(document_id: uuid.UUID):
    _require_document(document_id)
    extracted_at, items = load_flooring(document_id)
    return FlooringSchedule(document_id=str(document_id), extracted_at=extracted_at, items=items)


@app.get("/documents/{document_id}/flooring.csv")
def download_flooring_csv(document_id: uuid.UUID):
    document = _require_document(document_id)
    extracted_at, items = load_flooring(document_id)
    if extracted_at is None:
        raise HTTPException(status_code=404, detail="No flooring schedule yet. Extract it first.")

    filename = f"{_safe_filename(Path(document['filename']).stem)}-flooring.csv"
    return Response(
        content=flooring_csv(items),
        media_type="text/csv; charset=utf-8",
        # "attachment" makes the browser download it as a file with this name.
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe_filename(name: str) -> str:
    """Keep only simple characters so the download header can't be broken."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "document"


def flooring_csv(items: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)  # handles commas and quotes inside values
    writer.writerow(["code", "category", "product", "manufacturer", "rooms", "pages"])
    for item in items:
        writer.writerow([
            item["code"], item["category"], item["product"], item["manufacturer"],
            "; ".join(item["rooms"]), "; ".join(str(p) for p in item["pages"]),
        ])
    # The BOM at the start tells Excel the file is UTF-8 (so "é" or "×" show correctly).
    return "\ufeff" + buffer.getvalue()

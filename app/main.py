import uuid

from fastapi import FastAPI, HTTPException, UploadFile

from app.chunking import chunk_pages
from app.config import settings
from app.pdf_utils import InvalidPDFError, extract_pages
from app.schemas import Chunk, DocumentUploadResponse, PageText

app = FastAPI(title=settings.app_name)


@app.get("/")
def hello():
    return {"message": "Hello from PlanChat"}


# Simple health check, used later by Docker / Render to see if the app is alive.
@app.get("/health")
def health():
    return {"status": "ok"}


# A normal `def` (not `async def`): PDF parsing is slow CPU work, and FastAPI runs
# `def` endpoints in a thread pool so one big upload doesn't freeze the whole server.
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

    # Save under a random ID so two "plans.pdf" uploads never overwrite each other,
    # and a strange filename can't write outside the uploads folder.
    document_id = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{document_id}.pdf").write_bytes(pdf_bytes)

    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename or "upload.pdf",
        page_count=len(pages),
        pages=[PageText(**page, has_text=bool(page["text"])) for page in pages],
        chunk_count=len(chunks),
        chunks=[Chunk(**chunk) for chunk in chunks],
    )

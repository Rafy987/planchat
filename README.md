# PlanChat

AI assistant for construction plan sets and spec books (PDFs). Ask questions, get answers with page citations.

> Work in progress — currently Phase 4 (embeddings + pgvector storage).

## Tech (so far)
- Python 3.13, FastAPI, Uvicorn
- PyMuPDF for PDF text extraction
- fastembed with `BAAI/bge-small-en-v1.5` for embeddings (free, runs on CPU, no API key)
- Neon (cloud Postgres) + pgvector for storing chunks and their embeddings
- psycopg 3 (plain SQL, no ORM) with a connection pool
- pytest for tests

## Run locally (Windows)

```powershell
# 1. Create and activate a virtual environment
py -3.13 -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Copy env file and put your Neon connection string in DATABASE_URL
copy .env.example .env

# 4. Start the server
uvicorn app.main:app --reload
```

On first start the embedding model (~70 MB) is downloaded to `.cache/fastembed` and the database tables are created automatically.

Open http://localhost:8000/docs to see the API.

## Endpoints
| Method | Path      | Returns                                 |
|--------|-----------|-----------------------------------------|
| GET    | `/`       | `{"message": "Hello from PlanChat"}`    |
| GET    | `/health` | `{"status": "ok"}`                      |
| POST   | `/documents` | Upload a PDF; extracts, chunks, embeds and stores it |

### Upload a PDF

```powershell
curl.exe -F "file=@plans.pdf" http://localhost:8000/documents
```

```json
{
  "document_id": "00ed325b-9a37-4a20-8ab9-72a3f9593abd",
  "filename": "plans.pdf",
  "page_count": 2,
  "chunk_count": 2,
  "pages_without_text": []
}
```

- Files are saved to `uploads/<document_id>.pdf` (git-ignored).
- `pages_without_text` lists pages with no text, usually scanned images. OCR is not supported yet.
- Errors: `400` for empty, non-PDF or damaged files; `413` for files over 50 MB.

### How chunking works

The text is split into small pieces (**chunks**) so that later only the few pieces related to a question are sent to the AI, not the whole PDF.

- **Chunk size: 800 characters** (~1–2 paragraphs). Big enough to keep a sentence or table row together, small enough to stay on one topic.
- **Overlap: 150 characters** (~1–2 lines). Each chunk repeats the end of the previous one, so a fact that falls on a cut is still whole in one chunk.
- A chunk never crosses a page, so every chunk has exactly one page number for citations.
- Cuts happen at a paragraph break, then a line break, then a space, never in the middle of a word.
- Both numbers are settings (`CHUNK_SIZE`, `CHUNK_OVERLAP`) and will be tuned in the evaluation phase.

### How embeddings and storage work

- Each chunk is turned into an **embedding**: a list of 384 numbers that captures its meaning. Texts with similar meaning get similar numbers, so "What flooring is in Room 204?" lands close to "Room 204: Carpet Tile CPT-1" even with different words.
- **Model: `bge-small-en-v1.5` via fastembed.** Free, private (text never leaves the server), and it uses ONNX instead of PyTorch, so it fits on a small free-tier server.
- Chunks and embeddings are stored in Postgres with **pgvector**:
  - `documents(id, filename, page_count, created_at)`
  - `chunks(id, document_id, chunk_index, page_number, text, embedding vector(384))`, deleted automatically with their document
  - an **HNSW index** on `embedding` for fast similarity search
- A document and all its chunks are saved in **one transaction**: either everything is saved or nothing is.
- A **connection pool** reuses open database connections. Opening a new one to Neon takes seconds; reusing one is near-instant.

## Run tests

```powershell
pytest
```

Database tests use `DATABASE_URL` and delete every row they create. They are skipped if `DATABASE_URL` is not set. Most tests use a fake embedder for speed; one test uses the real model.

## License

This project is licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE).

PlanChat uses [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF text extraction, which is AGPL-3.0 licensed, so this project uses the same license. In short: anyone may use, change and share this code, but if they run a modified version as a web service, they must also share their source code.

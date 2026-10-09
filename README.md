# PlanChat

AI assistant for construction plan sets and spec books (PDFs). Ask questions, get answers with page citations.

> Work in progress — currently Phase 2 (PDF upload + text extraction).

## Tech (so far)
- Python 3.13, FastAPI, Uvicorn
- PyMuPDF for PDF text extraction
- pytest for tests
- Database: Neon (cloud Postgres + pgvector) — coming in a later phase

## Run locally (Windows)

```powershell
# 1. Create and activate a virtual environment
py -3.13 -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Copy env file and fill in values (not needed yet for Phase 1)
copy .env.example .env

# 4. Start the server
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs to see the API.

## Endpoints
| Method | Path      | Returns                                 |
|--------|-----------|-----------------------------------------|
| GET    | `/`       | `{"message": "Hello from PlanChat"}`    |
| GET    | `/health` | `{"status": "ok"}`                      |
| POST   | `/documents` | Upload a PDF; returns its text page by page |

### Upload a PDF

```powershell
curl.exe -F "file=@plans.pdf" http://localhost:8000/documents
```

```json
{
  "document_id": "e7b28945a43b47a6b067b439a88a4507",
  "filename": "plans.pdf",
  "page_count": 2,
  "pages": [
    {"page_number": 1, "text": "Sheet A-101", "has_text": true},
    {"page_number": 2, "text": "Room 204: Carpet Tile CPT-1", "has_text": true}
  ]
}
```

- Files are saved to `uploads/<document_id>.pdf` (git-ignored).
- `has_text: false` usually means a scanned page (image only). OCR is not supported yet.
- Errors: `400` for empty, non-PDF or damaged files; `413` for files over 50 MB.

## Run tests

```powershell
pytest
```

## License

This project is licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE).

PlanChat uses [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF text extraction, which is AGPL-3.0 licensed, so this project uses the same license. In short: anyone may use, change and share this code, but if they run a modified version as a web service, they must also share their source code.

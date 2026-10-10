# PlanChat

AI assistant for construction plan sets and spec books (PDFs). Ask questions, get answers with page citations.

> Work in progress — currently Phase 7 (flooring schedule extractor + CSV).

## Tech (so far)
- Python 3.13, FastAPI, Uvicorn
- PyMuPDF for PDF text extraction
- fastembed with `BAAI/bge-small-en-v1.5` for embeddings (free, runs on CPU, no API key)
- Neon (cloud Postgres) + pgvector for storing chunks and their embeddings
- psycopg 3 (plain SQL, no ORM) with a connection pool
- LLM: Groq (`qwen/qwen3.8-27b`, free tier) by default, OpenAI as optional fallback, both via the `openai` library
- Frontend: Next.js 16 + TypeScript + Tailwind CSS (in [`frontend/`](frontend/))
- pytest (backend) and Vitest (frontend) for tests

## Run locally (Windows)

```powershell
# 1. Create and activate a virtual environment
py -3.13 -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Copy env file; set DATABASE_URL (Neon) and GROQ_API_KEY (https://console.groq.com/keys)
copy .env.example .env

# 4. Start the server
uvicorn app.main:app --reload
```

On first start the embedding model (~70 MB) is downloaded to `.cache/fastembed` and the database tables are created automatically.

Open http://localhost:8000/docs to see the API.

## Run the frontend

Use a **second terminal** (the backend from the step above must be running):

```powershell
cd frontend
npm install
copy .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000, upload a PDF, then ask questions. Tap a **p. N** button in an answer to see the text from that page.

- Works on phones: single column, input fixed at the bottom, no zoom-in on tap.
- The backend only accepts browser requests from sites listed in `CORS_ORIGINS` (default `["http://localhost:3000"]`).

## Endpoints
| Method | Path      | Returns                                 |
|--------|-----------|-----------------------------------------|
| GET    | `/`       | `{"message": "Hello from PlanChat"}`    |
| GET    | `/health` | `{"status": "ok"}`                      |
| POST   | `/documents` | Upload a PDF; extracts, chunks, embeds and stores it |
| GET    | `/documents/{id}` | File name and page count of one document |
| POST   | `/documents/{id}/flooring` | Extract the flooring schedule with AI and save it (can take a minute) |
| GET    | `/documents/{id}/flooring` | The saved flooring schedule (no AI call) |
| GET    | `/documents/{id}/flooring.csv` | Download the schedule as a CSV file (opens in Excel) |
| POST   | `/ask` | Ask a question about one document; answer with page citations |

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

### Ask a question

```powershell
curl.exe -H "Content-Type: application/json" -d '{\"document_id\": \"<id from upload>\", \"question\": \"What flooring is in Room 204?\"}' http://localhost:8000/ask
```

```json
{
  "answer": "Room 204 has CPT-2 Carpet Tile [p. 2].",
  "sources": [{"page_number": 2, "text": "ROOM FINISH SCHEDULE - LEVEL 2
Room 201 Lobby: ..."}],
  "provider": "groq",
  "model": "qwen/qwen3.8-27b"
}
```

- Errors: `404` unknown document, `422` empty question or invalid ID, `503` AI service busy or unavailable (friendly message).

### How answering works

1. **Retrieve:** the question is embedded with the same model, and pgvector finds the **5 closest chunks** (`TOP_K`) of that one document by cosine distance.
2. **Prompt:** a short system prompt says to answer **only** from the excerpts and cite pages like `[p. 12]`. Each excerpt is labelled with its page. `temperature=0` and `max_tokens=300` keep answers factual and cheap.
3. **Check citations:** any `[p. N]` for a page that was **not** in the excerpts is removed (LLMs sometimes invent page numbers). `sources` lists the cited chunks.
4. **Fallback:** on a rate limit (429), token limit (413), context-too-long error, server error (5xx) or timeout, the app retries once with the other provider **if it has a key**. Otherwise it returns `503` with a friendly message. Other errors, such as a wrong API key, are not hidden.

Settings: `LLM_PROVIDER` (`groq` or `openai`), `GROQ_API_KEY`, `OPENAI_API_KEY`, `GROQ_MODEL`, `OPENAI_MODEL`, `TOP_K`. Keys are stored as `SecretStr`, so they never show up if settings are printed.

**Why `qwen/qwen3.8-27b`:** Groq no longer serves LLaMA chat models. In a side-by-side test, Qwen answered correctly with citations, while `gpt-oss-20b` missed facts on a second page and used special Unicode hyphens (`CPT‑1`) that would break later matching.

### Flooring schedule

On the chat page, tap **Flooring** → **Extract flooring schedule**. You get one row per product code:

| code | category | product | manufacturer | rooms | pages |
|---|---|---|---|---|---|
| LVP-1 | resilient | Luxury vinyl plank, Tarkett 'Contour', Weathered Oak | Tarkett | 102 Reception; 103 Corridor; 107 Staff Lounge | 3; 4; 5 |
| RB-2 | base | Rubber base, 6" integral cove, Grey | Johnsonite | 104 Exam 1; 105 Exam 2 | 3; 4 |

How it works:

1. **Glossary, no AI ([app/flooring.py](app/flooring.py)):** knows plan abbreviations. LVT, LVP, VCT, SV (sheet vinyl), rubber and linoleum are **resilient**; CPT is **carpet**; PT/QT are **tile**; RB is **base**, and so on. Short codes only count with a number (`RB-1`, not "RB"), and `PTAC-1` is not porcelain tile. It picks out only the chunks that mention flooring, so the AI never reads unrelated pages.
2. **AI in small batches:** those chunks go to the LLM in batches of about 1,500 tokens, and it replies in **JSON**. Groq's free tier allows only about 1,000 *output* tokens per minute, so answers are capped at 900 tokens. If an answer is cut off, the batch is split in half and retried. On a rate limit it waits (as long as Groq asks, else 10 s, up to 60 s) instead of failing.
3. **Anti-hallucination check:** an item is kept only if its code (or manufacturer) really appears on the pages it cites. Wrong page numbers are corrected.
4. **Merge:** the same code from different pages becomes one row (rooms from the finish schedule plus the manufacturer from the legend). The category comes from the glossary, not the AI.
5. Saved in the `flooring_items` table, so viewing it again or downloading the CSV costs nothing.

**Limitation:** drawings often have finish schedules as graphic tables, and PDF text extraction can scramble rows and columns. The AI can also miss an item on one run (run **Extract again**). Phase 8 will measure accuracy.

### Hybrid search (why "resilient flooring" now works)

Vector search alone missed questions like "Which rooms have resilient flooring?", because plans say "LVP-1", and the embedding model doesn't know that LVP is resilient. Now `/ask`:

- **Expands** flooring words in the question with the codes plans use (resilient → LVT, LVP, VCT, sheet vinyl…) for the search.
- **Adds keyword search:** up to 3 extra chunks that contain those exact codes (`KEYWORD_TOP_K`), next to the 5 closest by meaning.
- **Adds a one-line glossary** to the prompt, only for such questions, clearly marked as *not from the document*: "Resilient flooring = LVT, LVP, VCT…; other floor types are NOT resilient." Without the "NOT" part, the model also called carpet resilient.

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

## Accuracy

PlanChat is checked with 20 questions about 2 made-up sample documents (a clinic plan set and a library spec book), each with a known answer and page. Scoring uses simple rules, no AI judge: the answer must contain the right codes/room numbers and none of the wrong ones, and must cite the right page. "Not in the document" questions must say so.

<!-- EVAL:START -->
_Last run: 2026-10-10, 20 questions on 2 made-up sample documents. Details per question: [evaluation/results.md](evaluation/results.md)._

| | Hybrid search (used by the app) | Vector search only |
|---|---|---|
| Answer correct | **95% (19/20)** | 95% (19/20) |
| Cites the right page | **100% (20/20)** | 100% (20/20) |
| Right page found by search | **100% (17/17)** | 100% (17/17) |

| Flooring schedule extractor | Score |
|---|---|
| Product codes found | **93% (13/14)** |
| Correct category (of found) | 100% (13/13) |
| Exactly the right rooms (of found) | 100% (13/13) |
| Extra codes that shouldn't be there | 0  |
<!-- EVAL:END -->

**Limits:** 20 questions on documents I wrote is a small test. It shows the system works and catches regressions, but it doesn't prove accuracy on every real plan set. LLM answers can vary slightly between runs.

## Run tests

```powershell
pytest
```

Database tests use `DATABASE_URL` and delete every row they create. They are skipped if `DATABASE_URL` is not set. Most tests use a fake embedder for speed; one test uses the real model. LLM calls are always faked in tests (no API cost, no key needed).

## License

This project is licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE).

PlanChat uses [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF text extraction, which is AGPL-3.0 licensed, so this project uses the same license. In short: anyone may use, change and share this code, but if they run a modified version as a web service, they must also share their source code.

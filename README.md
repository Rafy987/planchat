# PlanChat

AI assistant for construction plan sets and spec books (PDFs). Ask questions, get answers with page citations.

> Work in progress — currently Phase 1 (project setup).

## Tech (so far)
- Python 3.13, FastAPI, Uvicorn
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

## Run tests

```powershell
pytest
```

# PlanChat — Project Guide for Claude

## What this project is
PlanChat is an AI assistant for construction plan sets and spec books (PDFs).
- User uploads a PDF (often 100+ pages)
- User asks questions like "What flooring is in Room 204?" or "Which rooms have carpet tile?"
- App answers ONLY from the document, with page-number citations
- "Extract flooring schedule" button: pulls all flooring products into a table (code, product, manufacturer, rooms) and exports CSV

This is a portfolio project. It must be real, deployed with a live link, and have a clean README.

## About me (the developer)
- Software Engineering graduate, comfortable with JavaScript/React/Node; newer to Python, FastAPI, Docker, vector DBs
- I am learning while building. I must understand every part for job interviews.

## How to work with me (IMPORTANT)
- Build ONE small feature at a time. Do not build the whole app in one go.
- Before writing code, tell me the plan in 3–5 short bullet points and wait for my OK.
- After each feature, explain what you did in simple Roman Urdu / simple English, short bullets, no heavy jargon.
- Explain WHY you chose something (e.g. chunk size, library choice), so I can answer interview questions.
- Write tests (pytest) with every backend feature and run them.
- Make small git commits with clear messages after each working feature.
- Never put API keys in code. Use a `.env` file and keep `.env` in `.gitignore`. Provide `.env.example`.

## Tech stack
- Backend: Python 3.13, FastAPI
- PDF reading: pypdf or PyMuPDF
- Database: Neon (cloud PostgreSQL with pgvector). Connection string goes in `.env` as `DATABASE_URL`
- LLM: Groq API (qwen/qwen3.8-27b; Groq retired its LLaMA chat models), OpenAI optional fallback via LLM_PROVIDER
- Embeddings: a free/open embedding model (e.g. sentence-transformers) or an embeddings API — discuss with me first
- Frontend: Next.js + TypeScript + Tailwind (later phase)
- Testing: pytest (backend), Postman collection for API
- DevOps: Dockerfile (built and tested in GitHub Codespaces), GitHub Actions (run tests on every push)
- Deploy: Render or Railway (backend), Neon (DB), Vercel (frontend)

## Dev environment
- Docker does NOT work on my laptop. Local dev uses a Python 3.13 virtual env (`.venv`), no Docker.
- Database is Neon in the cloud, not a local Postgres container.
- Anything Docker-related (Dockerfile, builds, container tests) is done in GitHub Codespaces.

## Build phases (in order)
1. Project setup: folder structure, virtual env, FastAPI "hello" endpoint, pytest (Dockerfile added later and tested in Codespaces)
2. PDF upload endpoint: save file, extract text page by page
3. Chunking: split text into chunks, keep page numbers
4. Embeddings + store chunks in pgvector
5. Ask endpoint: question → find similar chunks → send to Groq → answer with page citations
6. Frontend (Next.js + TypeScript + Tailwind): upload page + chat page (moved up so a working UI exists early)
7. Flooring schedule extractor (agent tool) + CSV export
8. Evaluation: 20 test questions, measure accuracy, show score in README
9. Rate limiting + basic error handling
10. GitHub Actions CI, deploy, final README (live link, screenshot, architecture diagram, how to run)

## Rules
- Use only public or sample PDFs for testing and demo. No real client documents in the repo.
- Keep code simple and readable over clever.
- Add short comments where logic is not obvious.

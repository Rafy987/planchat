# PlanChat backend (FastAPI). Built and tested in GitHub Codespaces and in CI;
# deployed on Render. The frontend is deployed separately (Vercel).

# Same Python version as local development.
FROM python:3.13.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # numpy's math library starts one thread per CPU, each reserving memory;
    # one thread is plenty here and keeps us inside a 512 MB server.
    OPENBLAS_NUM_THREADS=1 \
    EMBEDDING_CACHE_DIR=/app/.cache/fastembed

WORKDIR /app

# Install dependencies first: this layer is cached and only rebuilt when
# requirements.txt changes, not on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a normal user, not root: if the app were ever exploited, the attacker
# couldn't change the system inside the container.
RUN useradd --create-home appuser \
    && mkdir -p /app/uploads /app/.cache \
    && chown -R appuser /app
USER appuser

# Download the embedding model (~70 MB) now, at build time, so the server starts
# fast and doesn't download it on every restart.
RUN python -c "from app.embeddings import get_model; get_model()"

EXPOSE 8000

# Render tells the app which port to use in $PORT (8000 if not set).
# --no-proxy-headers: uvicorn must not trust X-Forwarded-For itself; the app reads
# the visitor IP safely (see TRUSTED_PROXY_HOPS in app/rate_limit.py).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]

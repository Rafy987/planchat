import uuid
from functools import cache

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import settings
from app.embeddings import EMBEDDING_DIM

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS documents (
    id          uuid PRIMARY KEY,
    filename    text NOT NULL,
    page_count  integer NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- ON DELETE CASCADE: deleting a document also deletes its chunks
    document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  integer NOT NULL,
    page_number  integer NOT NULL,
    text         text NOT NULL,
    embedding    vector({EMBEDDING_DIM}) NOT NULL,
    UNIQUE (document_id, chunk_index)
);

-- HNSW index: makes "find the most similar chunks" fast even with many chunks.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


@cache
def get_pool() -> ConnectionPool:
    """A pool keeps a few open connections and reuses them.

    Opening a new connection to Neon takes seconds (network + TLS + setup), so we
    pay that once instead of on every request.
    """
    return ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=5,
        # Runs once per new connection: lets us pass numpy arrays into `vector` columns.
        configure=register_vector,
        # Neon closes idle connections; check each one is alive before handing it out.
        check=ConnectionPool.check_connection,
        open=True,
    )


def get_connection():
    """Borrow a connection from the pool. Use as: `with get_connection() as conn:`.

    On leaving the `with` block the work is committed (or rolled back on error)
    and the connection goes back to the pool.
    """
    return get_pool().connection()


def close_pool() -> None:
    """Close all pooled connections (on server shutdown / end of tests)."""
    if get_pool.cache_info().currsize:  # only if the pool was ever created
        get_pool().close()
        get_pool.cache_clear()


def init_db() -> None:
    """Create the pgvector extension and tables if they don't exist yet."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    # The extension must exist before the pool can register the vector type.
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    with get_connection() as conn:
        conn.execute(SCHEMA_SQL)


def save_document(
    document_id: uuid.UUID,
    filename: str,
    page_count: int,
    chunks: list[dict],
    embeddings: list,
) -> None:
    """Save a document and all its chunks in ONE transaction: all or nothing."""
    with get_connection() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO documents (id, filename, page_count) VALUES (%s, %s, %s)",
            (document_id, filename, page_count),
        )
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (document_id, chunk_index, page_number, text, embedding)
                   VALUES (%s, %s, %s, %s, %s)""",
                [
                    (document_id, c["chunk_index"], c["page_number"], c["text"], emb)
                    for c, emb in zip(chunks, embeddings)
                ],
            )

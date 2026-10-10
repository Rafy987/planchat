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

-- When the flooring schedule was last extracted (NULL = never).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS flooring_extracted_at timestamptz;

CREATE TABLE IF NOT EXISTS flooring_items (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position      integer NOT NULL,  -- keeps the schedule's row order
    code          text NOT NULL,
    category      text NOT NULL,
    product       text NOT NULL,
    manufacturer  text NOT NULL,
    rooms         text[] NOT NULL,
    pages         integer[] NOT NULL
);
CREATE INDEX IF NOT EXISTS flooring_items_document_idx ON flooring_items (document_id);
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


def save_flooring(document_id: uuid.UUID, items: list[dict]) -> None:
    """Replace a document's flooring schedule (one transaction: all or nothing)."""
    with get_connection() as conn, conn.transaction():
        conn.execute("DELETE FROM flooring_items WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO flooring_items
                   (document_id, position, code, category, product, manufacturer, rooms, pages)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (document_id, i, it["code"], it["category"], it["product"],
                     it["manufacturer"], it["rooms"], it["pages"])
                    for i, it in enumerate(items)
                ],
            )
        conn.execute(
            "UPDATE documents SET flooring_extracted_at = now() WHERE id = %s", (document_id,)
        )


def load_flooring(document_id: uuid.UUID) -> tuple:
    """Return (extracted_at or None, items) for a document."""
    with get_connection() as conn:
        extracted_at = conn.execute(
            "SELECT flooring_extracted_at FROM documents WHERE id = %s", (document_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT code, category, product, manufacturer, rooms, pages
               FROM flooring_items WHERE document_id = %s ORDER BY position""",
            (document_id,),
        ).fetchall()
    keys = ["code", "category", "product", "manufacturer", "rooms", "pages"]
    return extracted_at, [dict(zip(keys, row)) for row in rows]

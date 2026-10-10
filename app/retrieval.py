import uuid

from app.db import get_connection


def get_document(document_id: uuid.UUID) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, filename, page_count FROM documents WHERE id = %s", (document_id,)
        ).fetchone()
    if row is None:
        return None
    return {"document_id": str(row[0]), "filename": row[1], "page_count": row[2]}


def document_exists(document_id: uuid.UUID) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM documents WHERE id = %s", (document_id,)).fetchone()
    return row is not None


def find_similar_chunks(document_id: uuid.UUID, question_embedding, top_k: int) -> list[dict]:
    """Return the `top_k` chunks of ONE document closest in meaning to the question.

    `<=>` is pgvector's cosine distance: 0 = same meaning, bigger = less related.
    ORDER BY ... LIMIT lets Postgres use the HNSW index to find them fast.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT page_number, text, embedding <=> %s AS distance
               FROM chunks
               WHERE document_id = %s
               ORDER BY embedding <=> %s
               LIMIT %s""",
            (question_embedding, document_id, question_embedding, top_k),
        ).fetchall()
    return [{"page_number": r[0], "text": r[1], "distance": float(r[2])} for r in rows]

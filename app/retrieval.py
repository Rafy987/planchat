import re
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
            """SELECT chunk_index, page_number, text, embedding <=> %s AS distance
               FROM chunks
               WHERE document_id = %s
               ORDER BY embedding <=> %s
               LIMIT %s""",
            (question_embedding, document_id, question_embedding, top_k),
        ).fetchall()
    return [
        {"chunk_index": r[0], "page_number": r[1], "text": r[2], "distance": float(r[3])}
        for r in rows
    ]


def find_chunks_by_keywords(
    document_id: uuid.UUID, keywords: list[str], limit: int, exclude: list[int]
) -> list[dict]:
    """Chunks containing any of the exact keywords/codes (e.g. "LVP", "CPT-2").

    This is the "keyword" half of hybrid search: embeddings miss abbreviations and
    codes, but plain text matching doesn't. Chunks mentioning the keywords most
    often come first (a finish schedule beats a passing mention).
    """
    if not keywords:
        return []
    # Postgres regex: \m and \M are word start/end; re.escape protects "-" etc.
    pattern = r"\m(" + "|".join(re.escape(k) for k in keywords) + r")\M"
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT chunk_index, page_number, text
               FROM chunks
               WHERE document_id = %s AND text ~* %s AND chunk_index <> ALL(%s)
               ORDER BY regexp_count(text, %s, 1, 'i') DESC, chunk_index
               LIMIT %s""",
            (document_id, pattern, exclude, pattern, limit),
        ).fetchall()
    return [{"chunk_index": r[0], "page_number": r[1], "text": r[2], "distance": None} for r in rows]


def get_all_chunks(document_id: uuid.UUID) -> list[dict]:
    """Every chunk of a document in reading order (used by the flooring extractor)."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT chunk_index, page_number, text FROM chunks
               WHERE document_id = %s ORDER BY chunk_index""",
            (document_id,),
        ).fetchall()
    return [{"chunk_index": r[0], "page_number": r[1], "text": r[2]} for r in rows]

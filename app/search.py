"""Finding the chunks to answer a question from. Used by /ask and by the evaluation."""

import uuid

from app.config import settings
from app.embeddings import embed_texts
from app.flooring import expand_question
from app.retrieval import find_chunks_by_keywords, find_similar_chunks


def search(document_id: uuid.UUID, question: str, hybrid: bool = True) -> tuple[list[dict], str | None]:
    """Return (chunks to send to the LLM, glossary hint or None).

    hybrid=True: flooring words in the question ("resilient") are expanded with the
    codes plans actually use (LVP, LVT, VCT...), and chunks containing those exact
    codes are added to the ones closest in meaning. hybrid=False is plain vector
    search, kept so the evaluation can measure what hybrid search adds.
    """
    if hybrid:
        expansion = expand_question(question)
    else:
        expansion = {"search_text": question, "keywords": [], "hint": None}

    # a) chunks closest in MEANING (embedding of the question + related terms)
    question_embedding = embed_texts([expansion["search_text"]])[0]
    chunks = find_similar_chunks(document_id, question_embedding, settings.top_k)
    # b) plus chunks containing the exact codes/terms, which embeddings often miss
    chunks += find_chunks_by_keywords(
        document_id,
        expansion["keywords"],
        limit=settings.keyword_top_k,
        exclude=[c["chunk_index"] for c in chunks],
    )
    return chunks, expansion["hint"]

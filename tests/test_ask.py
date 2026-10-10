import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main
from app import answer
from app.db import save_document
from app.embeddings import EMBEDDING_DIM
from app.llm import LLMUnavailableError
from app.main import app as fastapi_app
from app.retrieval import find_similar_chunks

client = TestClient(fastapi_app)


def direction(i: int):
    """A vector pointing in its own direction, so we control which chunk is 'closest'."""
    return np.eye(EMBEDDING_DIM, dtype=np.float32)[i]


def save_test_document(created: list, pages_and_vectors: list[tuple[int, str, int]]):
    """Save a document straight into the DB: [(page_number, text, direction), ...]."""
    document_id = uuid.uuid4()
    chunks = [
        {"chunk_index": i, "page_number": page, "text": text}
        for i, (page, text, _) in enumerate(pages_and_vectors)
    ]
    embeddings = [direction(d) for _, _, d in pages_and_vectors]
    save_document(document_id, "test.pdf", 3, chunks, embeddings)
    created.append(str(document_id))
    return document_id


@pytest.fixture
def plans(created_documents):
    return save_test_document(
        created_documents,
        [
            (1, "Sheet A-101 Floor Plan", 0),
            (2, "Room 204: Carpet Tile CPT-1", 1),
            (3, "Roof drain: cast iron", 2),
        ],
    )


# --- Retrieval ---


def test_closest_chunk_comes_first(plans):
    chunks = find_similar_chunks(plans, direction(1), top_k=5)

    assert chunks[0]["page_number"] == 2
    assert chunks[0]["text"] == "Room 204: Carpet Tile CPT-1"
    assert chunks[0]["distance"] == pytest.approx(0.0)


def test_top_k_limits_number_of_chunks(plans):
    assert len(find_similar_chunks(plans, direction(1), top_k=2)) == 2


def test_never_returns_chunks_from_another_document(plans, created_documents):
    save_test_document(created_documents, [(9, "OTHER DOC: Room 204 vinyl", 1)])

    chunks = find_similar_chunks(plans, direction(1), top_k=5)

    assert all("OTHER DOC" not in c["text"] for c in chunks)


# --- /ask endpoint (LLM is faked: no real API calls in tests) ---


@pytest.fixture
def fake_llm(monkeypatch):
    """Question embeds to direction 1 (the Room 204 chunk); LLM reply is set per test."""
    monkeypatch.setattr(app.main, "embed_texts", lambda texts: [direction(1)])
    replies = {}

    def fake_complete(system, user):
        replies["prompt"] = user
        if isinstance(replies["text"], Exception):
            raise replies["text"]
        return {"text": replies["text"], "provider": "groq", "model": "test-model"}

    monkeypatch.setattr(answer.llm, "complete", fake_complete)
    return replies


def ask(document_id, question="What flooring is in Room 204?"):
    return client.post("/ask", json={"document_id": str(document_id), "question": question})


def test_ask_returns_answer_with_checked_citations(plans, fake_llm):
    fake_llm["text"] = "Room 204 has Carpet Tile CPT-1 [p. 2] [p. 99]."

    response = ask(plans)

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Room 204 has Carpet Tile CPT-1 [p. 2].",  # invented [p. 99] removed
        "sources": [{"page_number": 2, "text": "Room 204: Carpet Tile CPT-1"}],
        "provider": "groq",
        "model": "test-model",
    }
    # The closest chunk was sent to the LLM, labelled with its page.
    assert "[p. 2] Room 204: Carpet Tile CPT-1" in fake_llm["prompt"]


def test_ask_unknown_document_is_404(database, fake_llm):
    response = ask(uuid.uuid4())

    assert response.status_code == 404


def test_ask_rejects_empty_question(plans):
    assert ask(plans, question="   ").status_code == 422


def test_ask_rejects_invalid_document_id():
    response = client.post("/ask", json={"document_id": "not-a-uuid", "question": "hi"})

    assert response.status_code == 422


def test_ask_returns_friendly_503_when_llm_unavailable(plans, fake_llm):
    fake_llm["text"] = LLMUnavailableError("The AI service is busy right now.")

    response = ask(plans)

    assert response.status_code == 503
    assert response.json() == {"detail": "The AI service is busy right now."}

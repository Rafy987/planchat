"""Flooring endpoints and hybrid search, against the real database (LLM faked)."""

import csv
import io
import json
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main
from app import answer, extractor
from app.db import save_document
from app.embeddings import EMBEDDING_DIM
from app.llm import LLMUnavailableError
from app.main import app as fastapi_app

client = TestClient(fastapi_app)


def direction(i: int):
    return np.eye(EMBEDDING_DIM, dtype=np.float32)[i]


@pytest.fixture
def plan_set(created_documents):
    """A small plan set: finish schedule, two spec pages, and unrelated pages."""
    document_id = uuid.uuid4()
    pages = [
        (1, "Sheet A-001 Cover, Berkeley sample project", 0),
        (2, "ROOM FINISH SCHEDULE\n205 Break Room: LVP-1, base RB-1\n206 Corridor: LVP-1", 1),
        (3, "Door hardware: lever handles, closers", 2),
        (4, "LVP-1: Mohawk Group, Natural Wood, Oak, 6x48 plank", 3),
        (5, "Roof drain: cast iron", 4),
    ]
    chunks = [{"chunk_index": i, "page_number": p, "text": t} for i, (p, t, _) in enumerate(pages)]
    save_document(document_id, "Sample Plans, Rev 1.pdf", 5, chunks, [direction(d) for *_, d in pages])
    created_documents.append(str(document_id))
    return document_id


@pytest.fixture
def fake_extractor_llm(monkeypatch):
    replies = []

    def fake_complete(system, user, **kwargs):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"text": reply, "provider": "groq", "model": "test"}

    monkeypatch.setattr(extractor.llm, "complete", fake_complete)
    return replies


LVP_REPLY = json.dumps({"items": [
    {"code": "LVP-1", "product": "", "manufacturer": "", "rooms": ["205 Break Room", "206 Corridor"], "pages": [2]},
    {"code": "LVP-1", "product": "Natural Wood, Oak, 6x48 plank", "manufacturer": "Mohawk Group", "rooms": [], "pages": [4]},
    {"code": "RB-1", "product": "rubber base", "manufacturer": "", "rooms": ["205 Break Room"], "pages": [2]},
]})


# --- Flooring endpoints ---


def test_schedule_is_empty_before_extraction(plan_set):
    body = client.get(f"/documents/{plan_set}/flooring").json()

    assert body["extracted_at"] is None
    assert body["items"] == []


def test_extract_saves_and_returns_schedule(plan_set, fake_extractor_llm):
    fake_extractor_llm.append(LVP_REPLY)

    response = client.post(f"/documents/{plan_set}/flooring")

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_at"] is not None
    assert body["items"] == [
        {"code": "LVP-1", "category": "resilient", "product": "Natural Wood, Oak, 6x48 plank",
         "manufacturer": "Mohawk Group", "rooms": ["205 Break Room", "206 Corridor"], "pages": [2, 4]},
        {"code": "RB-1", "category": "base", "product": "rubber base",
         "manufacturer": "", "rooms": ["205 Break Room"], "pages": [2]},
    ]
    # Saved: a GET now returns the same items without calling the LLM again.
    assert client.get(f"/documents/{plan_set}/flooring").json()["items"] == body["items"]


def test_extracting_again_replaces_the_old_schedule(plan_set, fake_extractor_llm):
    fake_extractor_llm.append(LVP_REPLY)
    client.post(f"/documents/{plan_set}/flooring")
    fake_extractor_llm.append(json.dumps({"items": [
        {"code": "RB-1", "product": "", "manufacturer": "", "rooms": [], "pages": [2]}
    ]}))

    body = client.post(f"/documents/{plan_set}/flooring").json()

    assert [i["code"] for i in body["items"]] == ["RB-1"]


def test_extract_returns_friendly_503_when_ai_is_busy(plan_set, fake_extractor_llm):
    fake_extractor_llm.append(LLMUnavailableError("The AI service is busy right now."))

    response = client.post(f"/documents/{plan_set}/flooring")

    assert response.status_code == 503
    assert response.json()["detail"] == "The AI service is busy right now."
    # Nothing was saved.
    assert client.get(f"/documents/{plan_set}/flooring").json()["extracted_at"] is None


def test_csv_download(plan_set, fake_extractor_llm):
    fake_extractor_llm.append(LVP_REPLY)
    client.post(f"/documents/{plan_set}/flooring")

    response = client.get(f"/documents/{plan_set}/flooring.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    # The odd filename "Sample Plans, Rev 1.pdf" becomes a safe download name.
    assert response.headers["content-disposition"] == 'attachment; filename="Sample_Plans_Rev_1-flooring.csv"'
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # BOM so Excel reads UTF-8 correctly
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows == [
        ["code", "category", "product", "manufacturer", "rooms", "pages"],
        # The comma inside the product is kept safe by CSV quoting.
        ["LVP-1", "resilient", "Natural Wood, Oak, 6x48 plank", "Mohawk Group", "205 Break Room; 206 Corridor", "2; 4"],
        ["RB-1", "base", "rubber base", "", "205 Break Room", "2"],
    ]


def test_csv_before_extraction_is_404(plan_set):
    response = client.get(f"/documents/{plan_set}/flooring.csv")

    assert response.status_code == 404
    assert "Extract it first" in response.json()["detail"]


@pytest.mark.parametrize("method, path", [
    ("get", "/flooring"), ("post", "/flooring"), ("get", "/flooring.csv"),
])
def test_unknown_document_is_404(database, method, path):
    response = getattr(client, method)(f"/documents/{uuid.uuid4()}{path}")

    assert response.status_code == 404


def test_deleting_document_deletes_its_schedule(plan_set, fake_extractor_llm, db):
    fake_extractor_llm.append(LVP_REPLY)
    client.post(f"/documents/{plan_set}/flooring")

    db.execute("DELETE FROM documents WHERE id = %s", (plan_set,))

    count = db.execute(
        "SELECT count(*) FROM flooring_items WHERE document_id = %s", (plan_set,)
    ).fetchone()[0]
    assert count == 0


# --- Hybrid search in /ask (your real bug: "resilient" found nothing) ---


@pytest.fixture
def capture_prompt(monkeypatch):
    """Fake LLM that records the prompt. The question 'means' page 3 (door hardware),
    so vector search alone would NOT find the LVP pages."""
    monkeypatch.setattr(app.main, "embed_texts", lambda texts: [direction(2)])
    monkeypatch.setattr(app.main.settings, "top_k", 1)
    seen = {}

    def fake_complete(system, user):
        seen["prompt"] = user
        return {"text": "Rooms 205 and 206 have LVP-1 [p. 2].", "provider": "groq", "model": "test"}

    monkeypatch.setattr(answer.llm, "complete", fake_complete)
    return seen


def test_resilient_question_finds_lvp_chunks_by_keyword(plan_set, capture_prompt):
    response = client.post(
        "/ask", json={"document_id": str(plan_set), "question": "Which rooms have resilient flooring?"}
    )

    assert response.status_code == 200
    prompt = capture_prompt["prompt"]
    assert "[p. 2] ROOM FINISH SCHEDULE" in prompt  # found by keyword "LVP"
    assert "Glossary (general knowledge, NOT from the document; don't cite it): Resilient flooring = LVT, LVP" in prompt
    assert response.json()["sources"][0]["page_number"] == 2


def test_normal_question_gets_no_keyword_chunks_or_hint(plan_set, capture_prompt):
    client.post("/ask", json={"document_id": str(plan_set), "question": "What door handles are used?"})

    prompt = capture_prompt["prompt"]
    assert "ROOM FINISH SCHEDULE" not in prompt
    assert "Glossary" not in prompt

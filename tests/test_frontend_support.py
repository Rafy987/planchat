"""Backend features the frontend needs: CORS and reading one document's info."""

import uuid

from fastapi.testclient import TestClient

from app.db import save_document
from app.main import app

client = TestClient(app)


def test_cors_allows_the_frontend():
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_blocks_unknown_websites():
    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_allows_posting_json():
    # Before a JSON POST, browsers first send an OPTIONS "may I?" request.
    response = client.options(
        "/ask",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_read_document_returns_name_and_page_count(created_documents):
    document_id = uuid.uuid4()
    save_document(document_id, "spec.pdf", 12, [], [])
    created_documents.append(str(document_id))

    response = client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(document_id),
        "filename": "spec.pdf",
        "page_count": 12,
    }


def test_read_unknown_document_is_404(database):
    assert client.get(f"/documents/{uuid.uuid4()}").status_code == 404


def test_read_document_with_invalid_id_is_422():
    assert client.get("/documents/not-a-uuid").status_code == 422

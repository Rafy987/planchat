import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient

import app.main
from app.config import settings
from app.embeddings import EMBEDDING_DIM
from app.main import app as fastapi_app

client = TestClient(fastapi_app)

# Known text for each page, so tests can check every page number matches its text.
SAMPLE_PAGES = [
    "Sheet A-101 Floor Plan Level 2",
    "Room 204: Carpet Tile CPT-1",
    "Flooring Schedule: CPT-1 Interface, LVT-2 Shaw",
]


def make_pdf(page_texts: list[str]) -> bytes:
    """Build a small PDF in memory, one page per string (no PDF file in the repo)."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def fake_embed_texts(texts: list[str]) -> list:
    """Stand-in for the real model: fast, no download. Vector i is filled with i+1."""
    return [np.full(EMBEDDING_DIM, i + 1, dtype=np.float32) for i in range(len(texts))]


@pytest.fixture(autouse=True)
def test_setup(tmp_path, monkeypatch):
    """Save uploads to a temp folder and use the fake embedder in every test here."""
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    monkeypatch.setattr(app.main, "embed_texts", fake_embed_texts)
    return tmp_path


def upload(content: bytes, filename: str = "plans.pdf", created: list | None = None):
    response = client.post(
        "/documents", files={"file": (filename, content, "application/pdf")}
    )
    if created is not None and response.status_code == 200:
        created.append(response.json()["document_id"])  # so cleanup deletes it
    return response


# --- Successful uploads (need the database) ---


def test_upload_returns_summary(created_documents):
    response = upload(make_pdf(SAMPLE_PAGES + [""]), created=created_documents)

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "plans.pdf"
    assert body["page_count"] == 4
    assert body["chunk_count"] == 3  # the empty 4th page gives no chunk
    assert body["pages_without_text"] == [4]


def test_upload_saves_document_row(created_documents, db):
    body = upload(make_pdf(SAMPLE_PAGES), created=created_documents).json()

    row = db.execute(
        "SELECT filename, page_count FROM documents WHERE id = %s", (body["document_id"],)
    ).fetchone()
    assert row == ("plans.pdf", 3)


def test_upload_saves_chunks_with_page_numbers_and_embeddings(created_documents, db):
    body = upload(make_pdf(SAMPLE_PAGES), created=created_documents).json()

    rows = db.execute(
        """SELECT chunk_index, page_number, text, embedding FROM chunks
           WHERE document_id = %s ORDER BY chunk_index""",
        (body["document_id"],),
    ).fetchall()

    assert [(r[0], r[1], r[2]) for r in rows] == [
        (0, 1, SAMPLE_PAGES[0]),
        (1, 2, SAMPLE_PAGES[1]),
        (2, 3, SAMPLE_PAGES[2]),
    ]
    # Each chunk got its own embedding (384 numbers) from the fake embedder.
    for i, row in enumerate(rows):
        embedding = row[3].to_numpy()
        assert embedding.shape == (EMBEDDING_DIM,)
        assert np.allclose(embedding, i + 1)


def test_upload_saves_file_to_disk(created_documents, test_setup):
    pdf_bytes = make_pdf(SAMPLE_PAGES)
    body = upload(pdf_bytes, created=created_documents).json()

    saved = test_setup / f"{body['document_id']}.pdf"
    assert saved.read_bytes() == pdf_bytes


def test_deleting_document_also_deletes_its_chunks(created_documents, db):
    document_id = upload(make_pdf(SAMPLE_PAGES), created=created_documents).json()["document_id"]

    db.execute("DELETE FROM documents WHERE id = %s", (document_id,))

    count = db.execute(
        "SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)
    ).fetchone()[0]
    assert count == 0


def test_nothing_saved_if_database_save_fails(created_documents, db, test_setup, monkeypatch):
    # Give the LAST chunk a vector of the wrong size. Postgres rejects it, so the save
    # fails after the document row and the first chunks were already inserted.
    def broken_embedder(texts):
        vectors = fake_embed_texts(texts)
        vectors[-1] = np.ones(3, dtype=np.float32)
        return vectors

    monkeypatch.setattr(app.main, "embed_texts", broken_embedder)

    with pytest.raises(Exception, match="dimensions"):
        upload(make_pdf(SAMPLE_PAGES), filename="should-not-exist.pdf")

    # The transaction was rolled back: no document row, and no file on disk.
    count = db.execute(
        "SELECT count(*) FROM documents WHERE filename = 'should-not-exist.pdf'"
    ).fetchone()[0]
    assert count == 0
    assert list(test_setup.iterdir()) == []


# --- Rejected uploads (no database needed) ---


def test_rejects_non_pdf_even_with_pdf_name():
    response = upload(b"hello, I am a text file", filename="fake.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "File is not a PDF"


def test_rejects_empty_file():
    response = upload(b"")

    assert response.status_code == 400
    assert response.json()["detail"] == "File is empty"


def test_rejects_damaged_pdf():
    response = upload(b"%PDF-1.7 this is not really a pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "PDF is damaged or unreadable"


def test_rejects_file_over_size_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # any non-empty file is too big

    response = upload(make_pdf(SAMPLE_PAGES))

    assert response.status_code == 413


def test_damaged_upload_is_not_saved(test_setup):
    upload(b"%PDF-1.7 broken")

    assert list(test_setup.iterdir()) == []

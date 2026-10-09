import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

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


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    """Save uploads to a temp folder during tests, not the real uploads/ folder."""
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    return tmp_path


def upload(content: bytes, filename: str = "plans.pdf"):
    return client.post(
        "/documents", files={"file": (filename, content, "application/pdf")}
    )


def test_upload_returns_text_for_each_page_with_page_numbers():
    response = upload(make_pdf(SAMPLE_PAGES))

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "plans.pdf"
    assert body["page_count"] == 3
    assert [p["page_number"] for p in body["pages"]] == [1, 2, 3]
    for page, expected in zip(body["pages"], SAMPLE_PAGES):
        assert page["text"] == expected
        assert page["has_text"] is True


def test_upload_saves_file_to_disk(temp_upload_dir):
    pdf_bytes = make_pdf(SAMPLE_PAGES)
    body = upload(pdf_bytes).json()

    saved = temp_upload_dir / f"{body['document_id']}.pdf"
    assert saved.read_bytes() == pdf_bytes


def test_page_without_text_is_flagged():
    body = upload(make_pdf(["Page one", ""])).json()

    assert body["pages"][1] == {"page_number": 2, "text": "", "has_text": False}


def test_upload_returns_chunks_with_page_numbers():
    body = upload(make_pdf(SAMPLE_PAGES + [""])).json()

    # 3 short pages with text -> one chunk each; the empty 4th page -> no chunk.
    assert body["chunk_count"] == 3
    assert [(c["page_number"], c["text"]) for c in body["chunks"]] == [
        (1, SAMPLE_PAGES[0]),
        (2, SAMPLE_PAGES[1]),
        (3, SAMPLE_PAGES[2]),
    ]


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


def test_damaged_upload_is_not_saved(temp_upload_dir):
    upload(b"%PDF-1.7 broken")

    assert list(temp_upload_dir.iterdir()) == []

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    chunk_count: int
    # Pages with no text are usually scanned images. We don't do OCR yet.
    pages_without_text: list[int]


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    page_count: int


class FlooringItem(BaseModel):
    code: str
    category: str
    product: str
    manufacturer: str
    rooms: list[str]
    pages: list[int]


class FlooringSchedule(BaseModel):
    document_id: str
    extracted_at: datetime | None  # None = not extracted yet
    items: list[FlooringItem]
    warnings: list[str] = []


class AskRequest(BaseModel):
    document_id: uuid.UUID  # an invalid ID is rejected with 422 automatically
    # Spaces are trimmed; empty questions are rejected; the max length saves tokens.
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Source(BaseModel):
    page_number: int
    text: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    provider: str | None  # which LLM answered; None if no LLM call was needed
    model: str | None

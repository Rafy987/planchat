import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    chunk_count: int
    # Pages with no text are usually scanned images. We don't do OCR yet.
    pages_without_text: list[int]


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

from pydantic import BaseModel


class PageText(BaseModel):
    page_number: int
    text: str
    # False usually means a scanned page (image only). We don't do OCR yet.
    has_text: bool


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    pages: list[PageText]

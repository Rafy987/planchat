from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    chunk_count: int
    # Pages with no text are usually scanned images. We don't do OCR yet.
    pages_without_text: list[int]

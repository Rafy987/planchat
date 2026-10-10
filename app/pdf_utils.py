import pymupdf


class InvalidPDFError(Exception):
    """Raised when the bytes are not a PDF we can open."""


class TooManyPagesError(Exception):
    """Raised when a PDF has more pages than we accept."""

    def __init__(self, page_count: int):
        super().__init__(f"PDF has {page_count} pages")
        self.page_count = page_count


def extract_pages(pdf_bytes: bytes, max_pages: int | None = None) -> list[dict]:
    """Return the text of every page as [{"page_number": 1, "text": "..."}, ...].

    Page numbers start at 1 so they match what people see in a PDF viewer.
    The page count is checked BEFORE reading any text, so a huge PDF is
    refused quickly instead of tying up the server.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise InvalidPDFError("Could not open PDF") from e

    with doc:
        if max_pages is not None and len(doc) > max_pages:
            raise TooManyPagesError(len(doc))
        return [
            {"page_number": index + 1, "text": page.get_text().strip()}
            for index, page in enumerate(doc)
        ]

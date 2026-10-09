import pymupdf


class InvalidPDFError(Exception):
    """Raised when the bytes are not a PDF we can open."""


def extract_pages(pdf_bytes: bytes) -> list[dict]:
    """Return the text of every page as [{"page_number": 1, "text": "..."}, ...].

    Page numbers start at 1 so they match what people see in a PDF viewer.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise InvalidPDFError("Could not open PDF") from e

    with doc:
        return [
            {"page_number": index + 1, "text": page.get_text().strip()}
            for index, page in enumerate(doc)
        ]

# Places we prefer to cut, best first: paragraph break, line break, space.
SEPARATORS = ["\n\n", "\n", " "]


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split one page of text into pieces of at most `chunk_size` characters.

    Each piece repeats about `overlap` characters from the end of the previous one,
    so a fact that sits across a cut is still whole in at least one piece.
    """
    if overlap >= chunk_size // 2:
        raise ValueError("overlap must be less than half of chunk_size")

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Look for a good cut point in the second half of the window, so chunks
        # don't come out tiny. Fall back to a hard cut (only for a giant "word").
        cut = end
        for sep in SEPARATORS:
            pos = text.rfind(sep, start + chunk_size // 2, end)
            if pos != -1:
                cut = pos
                break

        chunks.append(text[start:cut].strip())

        # Step back by `overlap` for the next chunk, then move forward to the start
        # of a line (best, keeps table rows whole) or else the start of a word.
        next_start = cut - overlap
        for sep in ("\n", " "):
            pos = text.find(sep, next_start, cut)
            if pos != -1:
                next_start = pos + 1
                break
        start = next_start

    return [c for c in chunks if c]


def chunk_pages(pages: list[dict], chunk_size: int, overlap: int) -> list[dict]:
    """Chunk every page separately, so each chunk belongs to exactly one page."""
    chunks = []
    for page in pages:
        for text in split_text(page["text"], chunk_size, overlap):
            chunks.append(
                {"chunk_index": len(chunks), "page_number": page["page_number"], "text": text}
            )
    return chunks

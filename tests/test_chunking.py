import pytest

from app.chunking import chunk_pages, split_text

SIZE = 800
OVERLAP = 150


def make_words(count: int, prefix: str = "word") -> str:
    """Unique words like 'word0001 word0002 ...' so we can spot a word cut in half."""
    return " ".join(f"{prefix}{i:04d}" for i in range(count))


def test_short_page_gives_one_chunk_with_its_page_number():
    pages = [{"page_number": 7, "text": "Room 204: Carpet Tile CPT-1"}]

    assert chunk_pages(pages, SIZE, OVERLAP) == [
        {"chunk_index": 0, "page_number": 7, "text": "Room 204: Carpet Tile CPT-1"}
    ]


def test_long_page_is_split_into_chunks_no_bigger_than_chunk_size():
    chunks = split_text(make_words(500), SIZE, OVERLAP)  # ~4500 characters

    assert len(chunks) > 1
    assert all(len(c) <= SIZE for c in chunks)


def test_neighbouring_chunks_share_the_overlap():
    chunks = split_text(make_words(500), SIZE, OVERLAP)

    for previous, current in zip(chunks, chunks[1:]):
        # The start of each chunk repeats text from the end of the one before it.
        assert current[:100] in previous[-OVERLAP:]


def test_no_word_is_cut_in_half_and_no_word_is_lost():
    text = make_words(500)
    original_words = set(text.split())

    chunks = split_text(text, SIZE, OVERLAP)
    chunk_words = [w for c in chunks for w in c.split()]

    assert set(chunk_words) <= original_words  # no half words like "rd0042"
    assert set(chunk_words) == original_words  # every word is in some chunk


def test_prefers_cutting_at_a_paragraph_break():
    paragraph_1 = make_words(50, "alpha")  # ~500 characters
    paragraph_2 = make_words(50, "beta")
    chunks = split_text(f"{paragraph_1}\n\n{paragraph_2}", SIZE, OVERLAP)

    assert chunks[0] == paragraph_1


def test_chunks_start_and_end_on_whole_lines_when_text_has_lines():
    # Like a room finish schedule: many short lines, one row per room.
    lines = [f"Room {n}: Carpet Tile CPT-1, base RB-1, ceiling ACT-1." for n in range(100, 160)]
    chunks = split_text("\n".join(lines), SIZE, OVERLAP)

    assert len(chunks) > 1
    for chunk in chunks:
        assert all(line in lines for line in chunk.split("\n"))  # no half rows


def test_chunks_never_mix_pages():
    pages = [
        {"page_number": 1, "text": make_words(200, "pageone")},
        {"page_number": 2, "text": make_words(200, "pagetwo")},
    ]

    for chunk in chunk_pages(pages, SIZE, OVERLAP):
        expected_prefix = "pageone" if chunk["page_number"] == 1 else "pagetwo"
        assert all(w.startswith(expected_prefix) for w in chunk["text"].split())


def test_chunk_index_counts_across_the_whole_document():
    pages = [
        {"page_number": 1, "text": make_words(200)},
        {"page_number": 2, "text": make_words(200)},
    ]
    chunks = chunk_pages(pages, SIZE, OVERLAP)

    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_empty_page_gives_no_chunks():
    pages = [{"page_number": 1, "text": ""}, {"page_number": 2, "text": "   \n "}]

    assert chunk_pages(pages, SIZE, OVERLAP) == []


def test_very_long_word_with_no_spaces_is_still_split():
    chunks = split_text("x" * 2000, SIZE, OVERLAP)

    assert all(len(c) <= SIZE for c in chunks)
    assert len(chunks) == 3


def test_rejects_overlap_too_big_for_chunk_size():
    with pytest.raises(ValueError):
        split_text("some text", chunk_size=100, overlap=60)

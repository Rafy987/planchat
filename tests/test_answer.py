from app import answer

CHUNKS = [
    {"page_number": 2, "text": "Room 204: Carpet Tile CPT-1", "distance": 0.2},
    {"page_number": 3, "text": "CPT-1: Interface Open Air 410", "distance": 0.3},
]


def test_prompt_labels_each_excerpt_with_its_page():
    prompt = answer.build_user_prompt("What flooring is in Room 204?", CHUNKS)

    assert "[p. 2] Room 204: Carpet Tile CPT-1" in prompt
    assert "[p. 3] CPT-1: Interface Open Air 410" in prompt
    assert prompt.endswith("Question: What flooring is in Room 204?")


def test_real_citations_are_kept_and_become_sources():
    text, sources = answer.check_citations("Carpet tile CPT-1 [p. 2] by Interface [p. 3].", CHUNKS)

    assert text == "Carpet tile CPT-1 [p. 2] by Interface [p. 3]."
    assert [s["page_number"] for s in sources] == [2, 3]


def test_invented_page_numbers_are_removed():
    text, sources = answer.check_citations("Carpet [p. 2]. Also tile [p. 99].", CHUNKS)

    assert text == "Carpet [p. 2]. Also tile."
    assert [s["page_number"] for s in sources] == [2]


def test_answer_without_citations_has_no_sources():
    text, sources = answer.check_citations("I couldn't find that in the document.", CHUNKS)

    assert sources == []


def test_no_chunks_means_no_llm_call(monkeypatch):
    def fail(*args):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr(answer.llm, "complete", fail)

    result = answer.answer_question("anything?", [])

    assert result["answer"] == answer.NOT_FOUND_ANSWER
    assert result["provider"] is None


def test_prompt_asks_for_only_matching_items_in_lists():
    # Evaluation Q8: the answer listed the right rooms, then named the wrong ones
    # in a note ("101 is carpet, not resilient"), which is noise for the user.
    assert "list ONLY the ones that match" in answer.SYSTEM_PROMPT

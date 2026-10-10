import json

import pytest

from app import extractor
from app.config import settings


def chunk(page: int, text: str, index: int = 0) -> dict:
    return {"chunk_index": index, "page_number": page, "text": text}


SCHEDULE = chunk(2, "ROOM FINISH SCHEDULE\n201 Lobby: PT-3\n205 Break Room: LVP-1, base RB-1\n206 Corridor: LVP-1", 0)
SPEC_LVP = chunk(4, "LVP-1: Mohawk Group, Natural Wood, Oak, 6x48 plank.\nRB-1: Johnsonite 4in rubber base", 1)
SPEC_PT = chunk(5, "PT-3: Daltile porcelain tile, 12x24, color Ash", 2)
ROOF = chunk(9, "Roof drain: cast iron body, dome strainer", 3)


# --- Batching ---


def test_batches_stay_under_token_budget():
    chunks = [chunk(i, "x" * 4000, i) for i in range(5)]  # ~1,000 tokens each

    batches = extractor.make_batches(chunks, max_tokens=2500)

    assert [len(b) for b in batches] == [2, 2, 1]


def test_huge_chunk_gets_its_own_batch():
    batches = extractor.make_batches([chunk(1, "x" * 20000), chunk(2, "small")], max_tokens=2500)

    assert [len(b) for b in batches] == [1, 1]


# --- Reading the LLM's JSON ---


def test_parse_items_cleans_values():
    text = json.dumps({"items": [
        {"code": "lvp 1", "product": " Oak plank ", "manufacturer": None, "rooms": ["205", " "], "pages": [2, "4", "x"]}
    ]})

    assert extractor.parse_items(text) == [
        {"code": "LVP-1", "product": "Oak plank", "manufacturer": "", "rooms": ["205"], "pages": [2, 4]}
    ]


@pytest.mark.parametrize("bad", ["not json", "[]", '{"rows": []}'])
def test_parse_items_rejects_unusable_json(bad):
    with pytest.raises(ValueError):
        extractor.parse_items(bad)


# --- Anti-hallucination check ---


def item(code="", product="", manufacturer="", rooms=None, pages=None) -> dict:
    return {"code": code, "product": product, "manufacturer": manufacturer,
            "rooms": rooms or [], "pages": pages or []}


def test_item_whose_code_is_in_the_text_is_kept():
    kept = extractor.verify_item(item("LVP-1", pages=[2, 4]), [SCHEDULE, SPEC_LVP])

    assert kept["pages"] == [2, 4]


def test_invented_code_is_dropped():
    assert extractor.verify_item(item("VCT-9", pages=[2]), [SCHEDULE, SPEC_LVP]) is None


def test_wrong_page_is_corrected_to_where_the_code_really_is():
    kept = extractor.verify_item(item("PT-3", pages=[4]), [SCHEDULE, SPEC_LVP, SPEC_PT])

    assert kept["pages"] == [2, 5]  # model said p. 4, but PT-3 is on pages 2 and 5


def test_item_without_code_is_checked_by_manufacturer():
    batch = [chunk(3, "Carpet tile by Interface, Open Air 410")]

    assert extractor.verify_item(item(product="Carpet tile", manufacturer="Interface"), batch)
    assert extractor.verify_item(item(product="Carpet tile", manufacturer="Shaw"), batch) is None


# --- Merging ---


def test_same_code_from_different_pages_is_merged():
    rows = extractor.merge_items([
        item("LVP-1", product="LVP", rooms=["205 Break Room", "206 Corridor"], pages=[2]),
        item("LVP-1", product="Natural Wood, Oak plank", manufacturer="Mohawk Group", pages=[4]),
        item("LVP-1", rooms=["206 corridor"], pages=[2]),  # same room, different case
    ])

    assert rows == [{
        "code": "LVP-1",
        "product": "Natural Wood, Oak plank",  # the more detailed text wins
        "manufacturer": "Mohawk Group",
        "rooms": ["205 Break Room", "206 Corridor"],
        "pages": [2, 4],
        "category": "resilient",
    }]


def test_rows_are_sorted_by_category():
    rows = extractor.merge_items([item("RB-1"), item("PT-3"), item("CPT-1"), item("LVP-1")])

    assert [r["code"] for r in rows] == ["LVP-1", "CPT-1", "PT-3", "RB-1"]


# --- Whole extraction with a fake LLM ---


@pytest.fixture
def fake_llm(monkeypatch):
    """Each LLM call returns the next reply from `replies`; prompts are recorded."""
    state = {"replies": [], "prompts": [], "kwargs": []}

    def fake_complete(system, user, **kwargs):
        state["prompts"].append(user)
        state["kwargs"].append(kwargs)
        return {"text": state["replies"].pop(0), "provider": "groq", "model": "test"}

    monkeypatch.setattr(extractor.llm, "complete", fake_complete)
    return state


def reply(*items) -> str:
    return json.dumps({"items": list(items)})


def test_extract_flooring_end_to_end(fake_llm):
    fake_llm["replies"] = [reply(
        item("LVP-1", rooms=["205 Break Room", "206 Corridor"], pages=[2]),
        item("LVP-1", product="Natural Wood, Oak", manufacturer="Mohawk Group", pages=[4]),
        item("PT-3", product="porcelain tile", manufacturer="Daltile", rooms=["201 Lobby"], pages=[2, 5]),
        item("VCT-7", rooms=["999"], pages=[2]),  # invented: not in the text
    )]

    result = extractor.extract_flooring([SCHEDULE, SPEC_LVP, SPEC_PT, ROOF])

    assert [(r["code"], r["category"], r["manufacturer"]) for r in result["items"]] == [
        ("LVP-1", "resilient", "Mohawk Group"),
        ("PT-3", "tile", "Daltile"),
    ]
    assert result["warnings"] == []
    # The roof drain chunk has no flooring words, so it was never sent (saves tokens).
    assert "Roof drain" not in fake_llm["prompts"][0]
    # Extraction asks for JSON and is allowed to wait on rate limits.
    assert fake_llm["kwargs"][0]["json_mode"] is True
    assert fake_llm["kwargs"][0]["max_wait_seconds"] == settings.flooring_max_wait_seconds


def test_no_flooring_text_means_no_llm_call(fake_llm):
    assert extractor.extract_flooring([ROOF]) == {"items": [], "warnings": []}
    assert fake_llm["prompts"] == []


def test_bad_json_is_retried_once(fake_llm):
    fake_llm["replies"] = ["oops, not json", reply(item("PT-3", pages=[5]))]

    result = extractor.extract_flooring([SPEC_PT])

    assert [r["code"] for r in result["items"]] == ["PT-3"]
    assert len(fake_llm["prompts"]) == 2


def test_cut_off_answer_splits_the_batch_in_half(fake_llm):
    # First answer for both chunks is cut off (bad JSON); each half then works.
    fake_llm["replies"] = [
        '{"items": [{"code": "LVP-1", "pro',
        reply(item("LVP-1", manufacturer="Mohawk Group", pages=[4])),
        reply(item("PT-3", manufacturer="Daltile", pages=[5])),
    ]

    result = extractor.extract_flooring([SPEC_LVP, SPEC_PT])

    assert [r["code"] for r in result["items"]] == ["LVP-1", "PT-3"]
    assert "PT-3" not in fake_llm["prompts"][1] and "LVP-1" not in fake_llm["prompts"][2]
    assert result["warnings"] == []


def test_single_chunk_with_bad_json_twice_is_skipped_with_a_warning(fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "flooring_batch_tokens", 10)  # one chunk per batch
    fake_llm["replies"] = ["bad", "still bad", reply(item("PT-3", pages=[5]))]

    result = extractor.extract_flooring([SPEC_LVP, SPEC_PT])

    assert [r["code"] for r in result["items"]] == ["PT-3"]
    assert result["warnings"] == ["Could not read the AI's answer for page 4; it was skipped."]


def test_output_limit_stays_under_groq_free_tier():
    # Groq refuses any request asking for more than 1,000 output tokens per minute.
    assert settings.flooring_max_output_tokens < 1000


def test_prompt_includes_concrete_and_coatings():
    # Evaluation: SC-1 (sealed concrete, no manufacturer) was sometimes skipped.
    assert "sealed or polished concrete" in extractor.SYSTEM_PROMPT
    assert "even with no manufacturer" in extractor.SYSTEM_PROMPT

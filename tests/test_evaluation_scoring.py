import pytest

from evaluation.scoring import contains_term, room_numbers, says_not_found, score_flooring, score_question


@pytest.mark.parametrize(
    "answer, term, expected",
    [
        ("Exam 1 has SV-1 sheet vinyl.", "SV-1", True),
        ("Exam 1 has sv 1.", "SV-1", True),  # case and space vs hyphen
        ("Exam 1 has SV‑1.", "SV-1", True),  # odd Unicode hyphen
        ("Room 1040 only.", "104", False),  # whole numbers only
        ("Toilet base is PT-1B.", "PT-1", False),  # PT-1 is not PT-1B
        ("Rooms **104** and 105", "104", True),  # markdown bold
        ("Outlet is 6 inch [p. 4].", "4", False),  # [p. 4] is not the answer "4"
        ("Made by Tarkett.", "tarkett", True),
    ],
)
def test_contains_term(answer, term, expected):
    assert contains_term(answer, term) is expected


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("I couldn't find that in the document.", True),
        ("I couldn’t find that in the document.", True),  # curly apostrophe
        ("The excerpts do not specify a fire rating.", True),
        ("The excerpts do not mention toilet partitions.", True),
        ("The fire rating is 1 hour [p. 3].", False),
        ("Rooms 104 and 105 use RB-2 [p. 3].", False),
    ],
)
def test_says_not_found(answer, expected):
    assert says_not_found(answer) is expected


LIST_QUESTION = {"must_include": ["104", "105"], "must_not_include": ["101"], "pages": [3]}


def test_correct_answer_scores_all_three():
    result = score_question(LIST_QUESTION, "Rooms 104 and 105 use RB-2 [p. 3].", [3], [1, 3])

    assert result == {"answer_ok": True, "citation_ok": True, "search_hit": True, "reason": ""}


def test_missing_and_extra_terms_explain_the_failure():
    result = score_question(LIST_QUESTION, "Rooms 101 and 104 [p. 3].", [3], [3])

    assert result["answer_ok"] is False
    assert result["reason"] == "missing 105; wrongly includes 101"


def test_wrong_page_and_search_miss_are_separate_checks():
    result = score_question(LIST_QUESTION, "Rooms 104 and 105 [p. 4].", [4], [4, 5])

    assert result["answer_ok"] is True
    assert result["citation_ok"] is False
    assert result["search_hit"] is False  # the right page never reached the AI


def test_not_in_document_question():
    question = {"not_in_document": True}

    good = score_question(question, "I couldn't find that in the document.", [], [1, 2])
    bad = score_question(question, "It is TPO [p. 2].", [2], [1, 2])

    assert good == {"answer_ok": True, "citation_ok": True, "search_hit": None, "reason": ""}
    assert bad["answer_ok"] is False and bad["citation_ok"] is False


def test_room_numbers():
    assert room_numbers(["205 Break Room", "Room 104 (Exam 1)", "Lobby"]) == {"205", "104"}


def test_score_flooring():
    expected = {
        "LVP-1": {"category": "resilient", "rooms": ["102", "103"]},
        "RB-1": {"category": "base", "rooms": ["101"]},
        "SC-1": {"category": "concrete/coating", "rooms": ["109"]},
    }
    items = [
        {"code": "LVP-1", "category": "resilient", "rooms": ["102 Reception", "103 Corridor"]},
        {"code": "rb 1", "category": "resilient", "rooms": ["101 Waiting", "102 Reception"]},
        {"code": "PNT-1", "category": "other", "rooms": []},
    ]

    assert score_flooring(expected, items) == {
        "expected": 3,
        "found": 2,
        "extra": ["PNT-1"],
        "missed": ["SC-1"],
        "category_ok": 1,  # RB-1 has the wrong category
        "rooms_ok": 1,  # RB-1 has an extra room
    }

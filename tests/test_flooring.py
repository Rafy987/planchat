import pytest

from app import flooring


@pytest.mark.parametrize(
    "code, description, category",
    [
        ("LVP-1", "", flooring.RESILIENT),
        ("lvt 2", "", flooring.RESILIENT),
        ("VCT", "", flooring.RESILIENT),
        ("SV-1", "", flooring.RESILIENT),
        ("CPT-2", "", flooring.CARPET),
        ("PT-3", "", flooring.TILE),
        ("WD-1", "", flooring.WOOD),
        ("SC-1", "", flooring.CONCRETE),
        ("RB-1", "", flooring.BASE),
        # Ambiguous CT: decided by the description.
        ("CT-1", "Interface carpet tile, 50x50", flooring.CARPET),
        ("CT-1", "Daltile ceramic tile 12x12", flooring.TILE),
        # Unknown code: decided by words in the description.
        ("F-1", "Luxury vinyl plank, Mohawk", flooring.RESILIENT),
        ("F-2", "4in rubber base, Johnsonite", flooring.BASE),  # base, not resilient
        ("F-3", "Broadloom carpet", flooring.CARPET),
        ("X-9", "Paint, eggshell", flooring.OTHER),
    ],
)
def test_categorize(code, description, category):
    assert flooring.categorize(code, description) == category


@pytest.mark.parametrize(
    "raw, expected",
    [("lvp 1", "LVP-1"), ("LVP1", "LVP-1"), ("LVP‑1", "LVP-1"), ("CPT-2A", "CPT-2A"), ("VCT", "VCT")],
)
def test_normalize_code(raw, expected):
    assert flooring.normalize_code(raw) == expected


def test_find_codes_in_plan_text():
    text = "Room 205: LVP-1, base RB 1. Room 206: LVP-1. Rooms 210-212: CPT2, VCT."

    assert flooring.find_codes(text) == ["LVP-1", "RB-1", "CPT-2", "VCT"]


@pytest.mark.parametrize(
    "text",
    [
        "PTAC-1 unit on roof",  # PTAC is a heater, not porcelain tile
        "RB alone without number",
        "SCHEDULE 40 PIPE",
        "EPA rated",
    ],
)
def test_no_false_codes(text):
    assert flooring.find_codes(text) == []


def test_mentions_flooring():
    assert flooring.mentions_flooring("Room 101: LVP-1")
    assert flooring.mentions_flooring("SECTION 09 65 19 - RESILIENT TILE FLOORING")
    assert flooring.mentions_flooring("Install carpet tile with adhesive")
    assert not flooring.mentions_flooring("Roof drain: cast iron, 4 inch outlet")


def test_expand_resilient_question_finds_lvp():
    result = flooring.expand_question("Which rooms have resilient flooring?")

    assert "LVP" in result["keywords"]
    assert "LVP" in result["search_text"]
    assert result["hint"].startswith("Resilient flooring = LVT, LVP")
    assert "other floor types are NOT resilient" in result["hint"]


def test_expand_question_with_exact_code():
    result = flooring.expand_question("Where is cpt-2 used?")

    assert "CPT-2" in result["keywords"]


def test_based_on_does_not_trigger_wall_base():
    result = flooring.expand_question("Based on the drawings, what is in Room 204?")

    assert result["hint"] is None


def test_plural_and_ed_forms_still_trigger():
    assert flooring.expand_question("Which rooms are carpeted?")["hint"] is not None
    assert flooring.expand_question("List the vinyls used")["hint"] is not None


def test_unrelated_question_is_not_expanded():
    result = flooring.expand_question("What size are the roof drains?")

    assert result == {"search_text": "What size are the roof drains?", "keywords": [], "hint": None}

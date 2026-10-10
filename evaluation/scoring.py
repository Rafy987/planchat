"""Scoring rules for the evaluation. Simple text rules, no AI judge:
free, the same result every time, and easy to explain."""

import re

from app.flooring import normalize_code

# Common ways to say "it's not in the document": couldn't find, cannot find,
# not mentioned/specified/listed, no information, do/does not specify/mention...
NOT_FOUND = re.compile(
    r"\b(?:could ?n[o']?t|can ?n[o']?t|can't|did ?n[o']?t) find"
    r"|\bnot (?:found|mentioned|specified|provided|listed|included)"
    r"|\bno (?:information|mention)"
    r"|\b(?:do|does)(?:n't| not) (?:specify|mention|include|list|say)"
)


def _normalize(text: str) -> str:
    """Uppercase, and treat spaces/hyphens alike: 'sv 1', 'SV-1', 'SV‑1' -> 'SV-1'."""
    return re.sub(r"[\s\-‐‑–—]+", "-", text.upper())


def _without_citations(answer: str) -> str:
    # "[p. 4]" must not count as the number 4 in the answer.
    return re.sub(r"\[p\.\s*\d+\]", " ", answer)


def contains_term(answer: str, term: str) -> bool:
    """Whole-term match: '104' matches 'Room 104' but not '1040'; 'PT-1' not 'PT-1B'."""
    text = _normalize(_without_citations(answer))
    pattern = rf"(?<![A-Z0-9]){re.escape(_normalize(term))}(?![A-Z0-9])"
    return re.search(pattern, text) is not None


def says_not_found(answer: str) -> bool:
    return NOT_FOUND.search(answer.lower().replace("’", "'")) is not None


def score_question(question: dict, answer: str, cited_pages: list[int], searched_pages: list[int]) -> dict:
    """Score one answer. Returns the three checks plus a short reason if wrong.

    search_hit is None for "not in document" questions (there is no right page).
    """
    if question.get("not_in_document"):
        found_nothing = says_not_found(answer)
        return {
            "answer_ok": found_nothing,
            "citation_ok": found_nothing and not cited_pages,
            "search_hit": None,
            "reason": "" if found_nothing else "should have said it couldn't find it",
        }

    missing = [t for t in question.get("must_include", []) if not contains_term(answer, t)]
    extra = [t for t in question.get("must_not_include", []) if contains_term(answer, t)]
    reasons = []
    if missing:
        reasons.append("missing " + ", ".join(missing))
    if extra:
        reasons.append("wrongly includes " + ", ".join(extra))

    expected_pages = set(question["pages"])
    return {
        "answer_ok": not missing and not extra,
        "citation_ok": bool(expected_pages & set(cited_pages)),
        "search_hit": bool(expected_pages & set(searched_pages)),
        "reason": "; ".join(reasons),
    }


def room_numbers(rooms: list[str]) -> set[str]:
    """'205 Break Room', 'Room 104 (Exam 1)' -> {'205', '104'}."""
    return {n for room in rooms for n in re.findall(r"\b\d{3,4}[A-Z]?\b", room.upper())}


def score_flooring(expected: dict, items: list[dict]) -> dict:
    """Compare an extracted flooring schedule with the true one."""
    found = {normalize_code(i["code"]): i for i in items if i["code"]}
    matched = [code for code in expected if code in found]
    return {
        "expected": len(expected),
        "found": len(matched),
        "extra": sorted(code for code in found if code not in expected),
        "missed": sorted(code for code in expected if code not in found),
        "category_ok": sum(found[c]["category"] == expected[c]["category"] for c in matched),
        "rooms_ok": sum(room_numbers(found[c]["rooms"]) == set(expected[c]["rooms"]) for c in matched),
    }

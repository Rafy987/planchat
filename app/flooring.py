"""Flooring glossary: recognises flooring codes and terms used on construction plans.

Plans write "LVP-1" or "VCT" instead of "resilient flooring", and the embedding
model doesn't know those mean the same thing. This module does, using plain rules
(free, predictable, testable) instead of asking the LLM.
"""

import re

RESILIENT = "resilient"
CARPET = "carpet"
TILE = "tile"
WOOD = "wood"
CONCRETE = "concrete/coating"
BASE = "base"
OTHER = "other"

# Code prefixes, e.g. "LVP" in "LVP-1". Long prefixes are distinctive enough on their own.
# Short ones (2 letters) only count WITH a number ("RB-1"), because "RB" or "SC" alone
# could mean anything on a drawing.
CODE_PREFIXES = {
    RESILIENT: {"long": ["LVT", "LVP", "VCT", "VET", "LIN", "RES"], "short": ["SV", "RF", "RT"]},
    CARPET: {"long": ["CPT", "CAR"], "short": ["CP"]},
    TILE: {"long": [], "short": ["PT", "QT", "TZ"]},
    WOOD: {"long": [], "short": ["WD", "HW"]},
    CONCRETE: {"long": [], "short": ["SC", "EP"]},
    BASE: {"long": [], "short": ["RB", "VB", "WB"]},
}

# Words that mean a flooring category. Used for products without a known code
# ("F-1: luxury vinyl plank") and to expand questions like "resilient flooring".
CATEGORY_TERMS = {
    RESILIENT: [
        "resilient", "luxury vinyl", "vinyl plank", "vinyl tile", "vinyl composition",
        "sheet vinyl", "vinyl sheet", "rubber flooring", "rubber tile", "rubber sheet",
        "linoleum", "LVT", "LVP", "VCT",
    ],
    CARPET: ["carpet", "broadloom", "walk-off", "walk off"],
    TILE: ["porcelain", "ceramic tile", "quarry tile", "terrazzo", "stone tile"],
    WOOD: ["hardwood", "engineered wood", "wood flooring", "bamboo flooring"],
    CONCRETE: [
        "sealed concrete", "polished concrete", "concrete sealer", "epoxy", "resinous flooring",
    ],
    BASE: ["rubber base", "vinyl base", "wall base", "cove base"],
}

# Extra words that only help FIND flooring text (not tied to one category).
GENERAL_TERMS = ["flooring", "floor finish", "finish schedule", "carpet tile"]


def _code_regex() -> re.Pattern:
    long_codes = [p for c in CODE_PREFIXES.values() for p in c["long"]]
    short_codes = [p for c in CODE_PREFIXES.values() for p in c["short"]] + ["CT"]
    # LVT, LVT-2, LVT 2, LVT2  |  RB-1, RB 1, RB1 (short codes need the number)
    return re.compile(
        rf"\b(?:(?P<long>{'|'.join(long_codes)})(?:[- ]?(?P<long_num>\d+[A-Z]?))?"
        rf"|(?P<short>{'|'.join(short_codes)})[- ]?(?P<short_num>\d+[A-Z]?))\b"
    )


CODE_PATTERN = _code_regex()
TERM_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(t) for terms in CATEGORY_TERMS.values() for t in terms)
    + "|"
    + "|".join(re.escape(t) for t in GENERAL_TERMS)
    + r")\b",
    re.IGNORECASE,
)


def normalize_code(code: str) -> str:
    """'lvp 1', 'LVP1', 'LVP‑1' (odd hyphen) -> 'LVP-1'."""
    code = code.upper().replace("‑", "-").replace("‐", "-").replace("–", "-").strip()
    match = re.fullmatch(r"([A-Z]+)[- ]?(\d+[A-Z]?)", code)
    return f"{match.group(1)}-{match.group(2)}" if match else code


def find_codes(text: str) -> list[str]:
    """All flooring codes in the text, normalised, in order, without repeats."""
    codes = []
    for m in CODE_PATTERN.finditer(text):
        prefix = m.group("long") or m.group("short")
        number = m.group("long_num") or m.group("short_num")
        code = f"{prefix}-{number}" if number else prefix
        if code not in codes:
            codes.append(code)
    return codes


def mentions_flooring(text: str) -> bool:
    """Quick, free check used to pick which chunks are worth sending to the LLM."""
    return bool(CODE_PATTERN.search(text) or TERM_PATTERN.search(text))


def _category_from_words(text: str) -> str | None:
    lowered = text.lower()
    # Base first: "rubber base" must not be counted as resilient "rubber flooring".
    for category in [BASE, CARPET, RESILIENT, TILE, WOOD, CONCRETE]:
        if any(term.lower() in lowered for term in CATEGORY_TERMS[category]):
            return category
    return None


def categorize(code: str, description: str = "") -> str:
    """Category from the code prefix, else from words in the product description.

    "CT" is ambiguous (ceramic tile OR carpet tile), so it's decided by the description.
    """
    prefix = re.match(r"[A-Z]+", normalize_code(code))
    prefix = prefix.group(0) if prefix else ""

    if prefix == "CT":
        return CARPET if "carpet" in description.lower() else TILE
    for category, prefixes in CODE_PREFIXES.items():
        if prefix in prefixes["long"] or prefix in prefixes["short"]:
            return category
    return _category_from_words(description) or OTHER


# Words in a QUESTION that mean "the user is asking about this category".
QUESTION_TRIGGERS = {
    RESILIENT: ["resilient", "vinyl", "lvt", "lvp", "vct", "linoleum", "rubber floor"],
    CARPET: ["carpet", "cpt", "broadloom"],
    TILE: ["porcelain", "ceramic", "quarry", "terrazzo", "tile floor"],
    WOOD: ["wood floor", "hardwood"],
    CONCRETE: ["concrete floor", "sealed concrete", "polished concrete", "epoxy"],
    BASE: ["base", "rubber base", "cove base"],
}

# What we tell the LLM a category includes (one short line, only when relevant).
CATEGORY_HINTS = {
    RESILIENT: "LVT, LVP, VCT, sheet vinyl, rubber flooring and linoleum",
    CARPET: "CPT, carpet tile and broadloom carpet",
    TILE: "porcelain (PT), ceramic, quarry tile and terrazzo",
    WOOD: "hardwood and engineered wood",
    CONCRETE: "sealed or polished concrete and epoxy/resinous coatings",
    BASE: "rubber base (RB), vinyl base and cove base",
}


def expand_question(question: str) -> dict:
    """Work out extra search words for a question.

    Returns {"search_text": question + related terms (for the embedding),
             "keywords": exact words/codes to also search for in the text,
             "hint": one line telling the LLM what the category includes, or None}.
    """
    lowered = question.lower()
    # Whole words only (plus plural/"-ed"), so "based on" doesn't count as "base".
    categories = [
        c for c, triggers in QUESTION_TRIGGERS.items()
        if any(re.search(rf"\b{re.escape(t)}(?:s|ed)?\b", lowered) for t in triggers)
    ]
    codes = find_codes(question.upper())

    keywords = list(codes)
    for category in categories:
        keywords += [t for t in CATEGORY_TERMS[category] if t not in keywords]

    hint = None
    if categories:
        # Saying what is NOT included stops the model from e.g. calling carpet "resilient".
        hint = " ".join(
            f"{c.capitalize()} flooring = {CATEGORY_HINTS[c]}; other floor types are NOT {c}."
            for c in categories
        )
    extra = [k for k in keywords if k.lower() not in lowered]
    search_text = f"{question} {' '.join(extra)}".strip()
    return {"search_text": search_text, "keywords": keywords, "hint": hint}

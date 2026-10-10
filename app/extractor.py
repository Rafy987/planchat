"""Flooring schedule extractor.

1. Pick chunks that mention flooring (free glossary check, no LLM).
2. Send them to the LLM in small batches; it returns JSON items.
3. Keep only items whose code/name really appears on the pages they cite.
4. Merge the same code found on different pages into one row.
"""

import json
import re

from app import llm
from app.config import settings
from app.flooring import categorize, mentions_flooring, normalize_code

SYSTEM_PROMPT = (
    "Extract every floor finish and wall base product from these construction document "
    'excerpts. Reply with JSON only: {"items":[{"code":"LVP-1","product":"luxury vinyl '
    'plank, Natural Wood, Oak","manufacturer":"Mohawk","rooms":["205 Break Room"],'
    '"pages":[2,4]}]}. One item per product code. rooms = rooms that use it. '
    'pages = the [p. N] where you saw it. Use "" or [] if unknown. '
    "Use ONLY the excerpts. No paint, ceilings or walls."
)

CATEGORY_ORDER = ["resilient", "carpet", "tile", "wood", "concrete/coating", "base", "other"]


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1  # rough rule: 1 token is about 4 characters of English


def make_batches(chunks: list[dict], max_tokens: int) -> list[list[dict]]:
    """Group chunks so each LLM request stays under `max_tokens` (Groq's free tier
    allows only ~8,000 tokens per minute). A huge chunk gets a batch of its own."""
    batches, current, size = [], [], 0
    for chunk in chunks:
        tokens = estimate_tokens(chunk["text"])
        if current and size + tokens > max_tokens:
            batches.append(current)
            current, size = [], 0
        current.append(chunk)
        size += tokens
    if current:
        batches.append(current)
    return batches


def parse_items(text: str) -> list[dict]:
    """Turn the LLM's JSON into clean items. Raises ValueError if it isn't usable."""
    data = json.loads(text)  # raises ValueError (JSONDecodeError) on bad JSON
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("JSON has no 'items' list")

    items = []
    for raw in data["items"]:
        if not isinstance(raw, dict):
            continue
        rooms = raw.get("rooms") if isinstance(raw.get("rooms"), list) else []
        pages = raw.get("pages") if isinstance(raw.get("pages"), list) else []
        items.append(
            {
                "code": normalize_code(str(raw.get("code") or "")),
                "product": str(raw.get("product") or "").strip(),
                "manufacturer": str(raw.get("manufacturer") or "").strip(),
                "rooms": [str(r).strip() for r in rooms if str(r).strip()],
                "pages": [int(p) for p in pages if str(p).isdigit()],
            }
        )
    return items


def _squash(text: str) -> str:
    """Lowercase and drop spaces/hyphens, so 'LVP 1', 'LVP-1' and 'lvp1' all match."""
    return re.sub(r"[\s\-‐‑–]", "", text.lower())


def verify_item(item: dict, batch: list[dict]) -> dict | None:
    """Keep an item only if its evidence (code, else manufacturer, else product)
    really appears in the text we sent. Fixes its page list to pages where it does.
    Returns None for invented items."""
    evidence = _squash(item["code"] or item["manufacturer"] or item["product"])
    if not evidence:
        return None

    page_texts: dict[int, str] = {}
    for chunk in batch:
        page_texts[chunk["page_number"]] = page_texts.get(chunk["page_number"], "") + " " + chunk["text"]
    pages_with_evidence = [p for p, t in page_texts.items() if evidence in _squash(t)]
    if not pages_with_evidence:
        return None

    # Prefer the pages the model cited; if it cited wrong ones, use where we found it.
    cited = [p for p in item["pages"] if p in pages_with_evidence]
    return {**item, "pages": cited or pages_with_evidence}


def _merge_key(item: dict) -> str:
    return item["code"] or _squash(item["product"])


def merge_items(items: list[dict]) -> list[dict]:
    """Combine rows for the same code (e.g. rooms from p. 2, manufacturer from p. 30)."""
    merged: dict[str, dict] = {}
    for item in items:
        key = _merge_key(item)
        if key not in merged:
            merged[key] = {**item, "rooms": [], "pages": []}
        row = merged[key]
        # Longer text usually means more detail ("Interface Open Air 410" > "Carpet").
        for field in ("product", "manufacturer"):
            if len(item[field]) > len(row[field]):
                row[field] = item[field]
        for room in item["rooms"]:
            if room.lower() not in (r.lower() for r in row["rooms"]):
                row["rooms"].append(room)
        row["pages"] = sorted(set(row["pages"]) | set(item["pages"]))

    rows = []
    for row in merged.values():
        category = categorize(row["code"], f"{row['product']} {row['manufacturer']}")
        rows.append({**row, "category": category})
    return sorted(rows, key=lambda r: (CATEGORY_ORDER.index(r["category"]), r["code"], r["product"]))


def _extract_batch(batch: list[dict], warnings: list[str]) -> list[dict]:
    """Extract items from one batch.

    Bad JSON usually means the answer was cut off at max_tokens (too many products
    in one batch). Then we split the batch in half and try each half. A single
    chunk gets one more try; if that fails too, it's skipped with a warning.
    """
    user = "\n\n".join(f"[p. {c['page_number']}] {c['text']}" for c in batch)
    attempts = 2 if len(batch) == 1 else 1
    for _ in range(attempts):
        result = llm.complete(
            SYSTEM_PROMPT,
            user,
            json_mode=True,
            max_tokens=settings.flooring_max_output_tokens,
            max_wait_seconds=settings.flooring_max_wait_seconds,
        )
        try:
            items = parse_items(result["text"])
        except ValueError:
            continue
        return [v for v in (verify_item(i, batch) for i in items) if v]

    if len(batch) > 1:
        middle = len(batch) // 2
        return _extract_batch(batch[:middle], warnings) + _extract_batch(batch[middle:], warnings)

    page = batch[0]["page_number"]
    warnings.append(f"Could not read the AI's answer for page {page}; it was skipped.")
    return []


def extract_flooring(chunks: list[dict]) -> dict:
    """Run the whole extraction for one document's chunks.

    Returns {"items": [...], "warnings": [...]}. Raises llm.LLMUnavailableError if
    the AI service can't be reached (nothing is saved in that case).
    """
    candidates = [c for c in chunks if mentions_flooring(c["text"])]
    items, warnings = [], []
    for batch in make_batches(candidates, settings.flooring_batch_tokens):
        items += _extract_batch(batch, warnings)
    return {"items": merge_items(items), "warnings": warnings}

import re

from app import llm

# Kept short on purpose: every token in the prompt costs money/limits on every question.
SYSTEM_PROMPT = (
    "You answer questions about a construction document. "
    "Use ONLY the excerpts given. Cite pages like [p. 12] after each fact. "
    "If the answer is not in the excerpts, say: I couldn't find that in the document. "
    "Be brief."
)

NOT_FOUND_ANSWER = "I couldn't find that in the document."
CITATION = re.compile(r"\[p\.\s*(\d+)\]")


def build_user_prompt(question: str, chunks: list[dict], hint: str | None = None) -> str:
    excerpts = "\n\n".join(f"[p. {c['page_number']}] {c['text']}" for c in chunks)
    # The hint (e.g. "Resilient flooring includes LVT, LVP...") is only added when the
    # question is about a flooring category, so normal questions cost no extra tokens.
    # Labelled clearly so the model doesn't think the hint is part of the document.
    note = f"Glossary (general knowledge, NOT from the document; don't cite it): {hint}\n\n" if hint else ""
    return f"Excerpts:\n{excerpts}\n\n{note}Question: {question}"


def check_citations(answer: str, chunks: list[dict]) -> tuple[str, list[dict]]:
    """Keep only citations to pages we actually gave the model.

    LLMs sometimes invent page numbers. A citation to a page that wasn't in the
    excerpts is removed from the answer. Returns (clean answer, sources).
    """
    given_pages = {c["page_number"] for c in chunks}

    def keep_if_real(match: re.Match) -> str:
        return match.group(0) if int(match.group(1)) in given_pages else ""

    answer = CITATION.sub(keep_if_real, answer)
    answer = re.sub(r"[ \t]+([.,;])", r"\1", answer)  # tidy "text ." left by removals
    answer = re.sub(r"[ \t]{2,}", " ", answer).strip()
    cited = {int(p) for p in CITATION.findall(answer)}
    sources = [
        {"page_number": c["page_number"], "text": c["text"]}
        for c in sorted(chunks, key=lambda c: c["page_number"])
        if c["page_number"] in cited
    ]
    return answer, sources


def answer_question(question: str, chunks: list[dict], hint: str | None = None) -> dict:
    """Ask the LLM using the retrieved chunks. Returns answer, sources, provider, model."""
    if not chunks:
        # No text in this document (e.g. scanned pages): don't spend tokens on it.
        return {"answer": NOT_FOUND_ANSWER, "sources": [], "provider": None, "model": None}

    result = llm.complete(SYSTEM_PROMPT, build_user_prompt(question, chunks, hint))
    answer, sources = check_citations(result["text"], chunks)
    return {
        "answer": answer,
        "sources": sources,
        "provider": result["provider"],
        "model": result["model"],
    }

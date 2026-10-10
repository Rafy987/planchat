"""Run the evaluation: python -m evaluation.run  (add --quick to skip the comparison)

1. Builds the made-up sample PDFs and saves them to Neon (like an upload).
2. Asks the 20 questions with hybrid search, then again with vector search only.
3. Extracts the flooring schedule of each sample and compares it to the truth.
4. Writes evaluation/results.md and the "Accuracy" section of README.md.
5. Deletes its sample documents from Neon again.

Uses the REAL search and LLM (Groq free tier), so it takes a few minutes.
"""

import argparse
import json
import re
import time
import uuid
from datetime import date
from pathlib import Path

from app.answer import answer_question
from app.chunking import chunk_pages
from app.config import settings
from app.db import close_pool, get_connection, init_db, save_document
from app.embeddings import embed_texts
from app.extractor import extract_flooring
from app.llm import LLMUnavailableError
from app.pdf_utils import extract_pages
from app.retrieval import get_all_chunks
from app.search import search
from evaluation.samples import SAMPLES, build_pdf, write_samples
from evaluation.scoring import score_flooring, score_question

HERE = Path(__file__).parent
README = HERE.parent / "README.md"
README_START, README_END = "<!-- EVAL:START -->", "<!-- EVAL:END -->"
LLM_WAIT = 60  # the evaluation may wait out rate limits; chat doesn't


def upload_sample(name: str) -> uuid.UUID:
    """Same steps as POST /documents: extract, chunk, embed, save."""
    filename, pages_text = SAMPLES[name]
    pages = extract_pages(build_pdf(pages_text))
    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    document_id = uuid.uuid4()
    save_document(document_id, filename, len(pages), chunks, embed_texts([c["text"] for c in chunks]))
    return document_id


def run_questions(questions: list[dict], doc_ids: dict, hybrid: bool) -> list[dict]:
    rows = []
    for q in questions:
        chunks, hint = search(doc_ids[q["doc"]], q["question"], hybrid=hybrid)
        try:
            result = answer_question(q["question"], chunks, hint, max_wait_seconds=LLM_WAIT)
        except LLMUnavailableError as error:
            result = {"answer": f"(error: {error.message})", "sources": []}
        cited = sorted({s["page_number"] for s in result["sources"]})
        searched = sorted({c["page_number"] for c in chunks})
        score = score_question(q, result["answer"], cited, searched)
        rows.append({**q, "answer": result["answer"], "cited": cited, "searched": searched, **score})
        mark = "OK  " if score["answer_ok"] else "FAIL"
        print(f"  {mark} Q{q['id']:>2} {q['question'][:55]:55} {score['reason']}")
    return rows


def summarize(rows: list[dict]) -> dict:
    with_page = [r for r in rows if r["search_hit"] is not None]
    return {
        "answer": sum(r["answer_ok"] for r in rows),
        "citation": sum(r["citation_ok"] for r in rows),
        "search": sum(r["search_hit"] for r in with_page),
        "total": len(rows),
        "search_total": len(with_page),
    }


def pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}% ({part}/{whole})" if whole else "n/a"


def one_line(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).replace("|", "/").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summary_table(summaries: dict, flooring: dict) -> str:
    lines = ["| | Hybrid search (used by the app) |" + (" Vector search only |" if "vector" in summaries else "")]
    lines.append("|---|---|" + ("---|" if "vector" in summaries else ""))
    for key, label in [("answer", "Answer correct"), ("citation", "Cites the right page"), ("search", "Right page found by search")]:
        total = "search_total" if key == "search" else "total"
        cells = [pct(s[key], s[total]) for s in summaries.values()]
        lines.append(f"| {label} | " + " | ".join(f"**{c}**" if i == 0 else c for i, c in enumerate(cells)) + " |")

    f = flooring
    lines += [
        "",
        "| Flooring schedule extractor | Score |",
        "|---|---|",
        f"| Product codes found | **{pct(f['found'], f['expected'])}** |",
        f"| Correct category (of found) | {pct(f['category_ok'], f['found'])} |",
        f"| Exactly the right rooms (of found) | {pct(f['rooms_ok'], f['found'])} |",
        f"| Extra codes that shouldn't be there | {len(f['extra'])} {', '.join(f['extra'])} |",
    ]
    return "\n".join(lines)


def write_results(summaries: dict, rows_by_mode: dict, flooring: dict, flooring_details: dict, seconds: float):
    today = date.today().isoformat()
    out = [
        "# Evaluation results",
        "",
        f"Run on {today} with `{settings.groq_model}` (Groq), top_k={settings.top_k}, "
        f"chunk size {settings.chunk_size}/{settings.chunk_overlap}. Took {round(seconds)} s. "
        "Re-run with `python -m evaluation.run`.",
        "",
        summary_table(summaries, flooring),
        "",
    ]
    for mode, rows in rows_by_mode.items():
        out += [
            f"## Questions: {'hybrid search' if mode == 'hybrid' else 'vector search only'}",
            "",
            "| # | Question | Answer | Cites page | Search hit | Answer given | Why wrong |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            hit = "–" if r["search_hit"] is None else ("✅" if r["search_hit"] else "❌")
            out.append(
                f"| {r['id']} | {one_line(r['question'])} | {'✅' if r['answer_ok'] else '❌'} | "
                f"{'✅' if r['citation_ok'] else '❌'} | {hit} | {one_line(r['answer'])} | {r['reason']} |"
            )
        out.append("")
    out += ["## Flooring extractor details", ""]
    for name, d in flooring_details.items():
        out.append(f"- **{name}**: found {d['found']}/{d['expected']}, missed {d['missed'] or 'none'}, "
                   f"extra {d['extra'] or 'none'}, right category {d['category_ok']}, right rooms {d['rooms_ok']}")
    (HERE / "results.md").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")

    readme = README.read_text(encoding="utf-8")
    section = (
        f"{README_START}\n_Last run: {today}, 20 questions on 2 made-up sample documents. "
        f"Details per question: [evaluation/results.md](evaluation/results.md)._\n\n"
        f"{summary_table(summaries, flooring)}\n{README_END}"
    )
    readme = re.sub(re.escape(README_START) + ".*?" + re.escape(README_END), lambda m: section, readme, flags=re.DOTALL)
    README.write_text(readme, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate PlanChat on made-up sample documents.")
    parser.add_argument("--quick", action="store_true", help="hybrid search only (skip vector-only comparison)")
    args = parser.parse_args()

    started = time.time()
    data = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    write_samples(HERE / "samples")  # so you can open the PDFs and check the answers yourself

    init_db()
    doc_ids = {}
    try:
        for name in SAMPLES:
            doc_ids[name] = upload_sample(name)
        print(f"Uploaded samples: {', '.join(SAMPLES)}")

        rows_by_mode = {}
        for mode in ["hybrid"] if args.quick else ["hybrid", "vector"]:
            print(f"\nQuestions ({mode} search):")
            rows_by_mode[mode] = run_questions(data["questions"], doc_ids, hybrid=(mode == "hybrid"))
        summaries = {mode: summarize(rows) for mode, rows in rows_by_mode.items()}

        print("\nFlooring extractor:")
        details = {}
        for name, doc_id in doc_ids.items():
            items = extract_flooring(get_all_chunks(doc_id))["items"]
            details[name] = score_flooring(data["flooring_schedules"][name], items)
            print(f"  {name}: {details[name]}")
        flooring = {k: sum(d[k] for d in details.values()) for k in ["expected", "found", "category_ok", "rooms_ok"]}
        flooring["extra"] = [f"{n}:{c}" for n, d in details.items() for c in d["extra"]]

        write_results(summaries, rows_by_mode, flooring, details, time.time() - started)
        print("\n" + summary_table(summaries, flooring))
        print("\nWrote evaluation/results.md and the Accuracy section of README.md")
    finally:
        # Always remove the sample documents again (chunks and schedules go with them).
        with get_connection() as conn:
            for doc_id in doc_ids.values():
                conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        close_pool()


if __name__ == "__main__":
    main()

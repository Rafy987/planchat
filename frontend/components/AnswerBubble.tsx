"use client";

import { useState } from "react";

import type { Source } from "@/lib/api";
import { splitCitations } from "@/lib/citations";

// Shows an answer where every [p. N] is a button. Tapping it shows the text
// from that page that the answer was based on; tapping again hides it.
export default function AnswerBubble({ answer, sources }: { answer: string; sources: Source[] }) {
  const [openPages, setOpenPages] = useState<number[]>([]);

  function togglePage(page: number) {
    setOpenPages((pages) =>
      pages.includes(page) ? pages.filter((p) => p !== page) : [...pages, page],
    );
  }

  return (
    <div className="max-w-[90%] rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
      <p className="leading-relaxed whitespace-pre-wrap">
        {splitCitations(answer).map((part, i) =>
          part.type === "text" ? (
            <span key={i}>{part.text}</span>
          ) : (
            <button
              key={i}
              type="button"
              onClick={() => togglePage(part.page)}
              aria-expanded={openPages.includes(part.page)}
              className={`mx-0.5 rounded-md px-1.5 py-0.5 text-xs font-semibold align-middle transition ${
                openPages.includes(part.page)
                  ? "bg-blue-600 text-white"
                  : "bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/50 dark:text-blue-300"
              }`}
            >
              p. {part.page}
            </button>
          ),
        )}
      </p>

      {openPages.map((page) => (
        <div
          key={page}
          className="mt-3 rounded-lg border-l-4 border-blue-500 bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800/60"
        >
          <p className="mb-1 font-semibold text-blue-700 dark:text-blue-300">Page {page}</p>
          {sources
            .filter((s) => s.page_number === page)
            .map((s, i) => (
              <p key={i} className="whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                {s.text}
              </p>
            ))}
        </div>
      ))}
    </div>
  );
}

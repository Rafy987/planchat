"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import {
  extractFlooring,
  flooringCsvUrl,
  getDocument,
  getFlooring,
  type DocumentInfo,
  type FlooringSchedule,
} from "@/lib/api";

const CATEGORY_STYLES: Record<string, string> = {
  resilient: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  carpet: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  tile: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  wood: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  "concrete/coating": "bg-stone-200 text-stone-800 dark:bg-stone-800 dark:text-stone-300",
  base: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
};

function CategoryBadge({ category }: { category: string }) {
  const style = CATEGORY_STYLES[category] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${style}`}>{category}</span>;
}

const dash = (value: string) => value || "—";
const pageList = (pages: number[]) => pages.map((p) => `p. ${p}`).join(", ");

export default function FlooringPage({ params }: PageProps<"/chat/[documentId]/flooring">) {
  const { documentId } = use(params);
  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [schedule, setSchedule] = useState<FlooringSchedule | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the document name and any schedule saved earlier (free, no AI call).
  useEffect(() => {
    getDocument(documentId).then(setDoc).catch((e: Error) => setError(e.message));
    getFlooring(documentId).then(setSchedule).catch((e: Error) => setError(e.message));
  }, [documentId]);

  async function runExtraction() {
    setExtracting(true);
    setError(null);
    try {
      setSchedule(await extractFlooring(documentId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExtracting(false);
    }
  }

  const extracted = schedule?.extracted_at != null;
  const items = schedule?.items ?? [];

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-4 py-4">
      <header className="flex items-center gap-3">
        <Link
          href={`/chat/${encodeURIComponent(documentId)}`}
          aria-label="Back to chat"
          className="rounded-lg px-2 py-1 text-xl hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          ←
        </Link>
        <div className="min-w-0">
          <h1 className="font-semibold">Flooring schedule</h1>
          <p className="truncate text-xs text-slate-500">{doc?.filename ?? "Loading…"}</p>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={runExtraction}
          disabled={extracting || schedule === null}
          className="rounded-xl bg-blue-600 px-4 py-2.5 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          {extracting ? "Extracting…" : extracted ? "Extract again" : "Extract flooring schedule"}
        </button>
        {extracted && items.length > 0 && (
          <a
            href={flooringCsvUrl(documentId)}
            className="rounded-xl border border-slate-300 px-4 py-2.5 font-semibold hover:border-blue-400 dark:border-slate-700"
          >
            Download CSV
          </a>
        )}
      </div>

      {extracting && (
        <p className="flex items-center gap-2 text-sm text-slate-500" role="status">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          Scanning every page for flooring. Big plan sets can take a minute or two.
        </p>
      )}

      {error && (
        <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {schedule?.warnings.map((warning) => (
        <p key={warning} className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          {warning}
        </p>
      ))}

      {!extracted && !extracting && schedule !== null && (
        <p className="text-slate-500">
          Find every floor finish and wall base in this document (codes like LVP-1, CPT-2, RB-1), with
          manufacturer, rooms and pages.
        </p>
      )}

      {extracted && items.length === 0 && !extracting && (
        <p className="text-slate-500">No flooring products were found in this document.</p>
      )}

      {items.length > 0 && (
        <>
          {/* Phones: one card per product. */}
          <ul className="space-y-3 md:hidden">
            {items.map((item, i) => (
              <li key={i} className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-lg font-bold">{dash(item.code)}</span>
                  <CategoryBadge category={item.category} />
                </div>
                <p className="mt-1">{dash(item.product)}</p>
                <p className="text-sm text-slate-500">{dash(item.manufacturer)}</p>
                <p className="mt-2 text-sm">
                  <span className="font-semibold">Rooms: </span>
                  {item.rooms.length ? item.rooms.join(", ") : "—"}
                </p>
                <p className="text-xs text-slate-500">{pageList(item.pages)}</p>
              </li>
            ))}
          </ul>

          {/* Tablets and computers: a table. */}
          <div className="hidden overflow-x-auto rounded-2xl ring-1 ring-slate-200 md:block dark:ring-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-100 text-xs uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                <tr>
                  {["Code", "Category", "Product", "Manufacturer", "Rooms", "Pages"].map((h) => (
                    <th key={h} className="px-3 py-2">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {items.map((item, i) => (
                  <tr key={i} className="align-top">
                    <td className="px-3 py-2 font-mono font-semibold whitespace-nowrap">{dash(item.code)}</td>
                    <td className="px-3 py-2"><CategoryBadge category={item.category} /></td>
                    <td className="px-3 py-2">{dash(item.product)}</td>
                    <td className="px-3 py-2">{dash(item.manufacturer)}</td>
                    <td className="px-3 py-2">{item.rooms.length ? item.rooms.join(", ") : "—"}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-slate-500">{pageList(item.pages)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { uploadDocument } from "@/lib/api";

const MAX_MB = 50; // same limit as the backend, checked here too for a faster message

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function chooseFile(chosen: File | null) {
    setError(null);
    if (chosen && chosen.size > MAX_MB * 1024 * 1024) {
      setError(`That file is larger than ${MAX_MB} MB.`);
      setFile(null);
      return;
    }
    setFile(chosen);
  }

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const result = await uploadDocument(file);
      router.push(`/chat/${encodeURIComponent(result.document_id)}`);
    } catch (e) {
      setError((e as Error).message);
      setUploading(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-10">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">PlanChat</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Upload a construction plan set or spec book (PDF), then ask questions about it. Every
          answer cites the page it came from.
        </p>
      </div>

      <form onSubmit={handleUpload} className="flex flex-col gap-4">
        {/* The whole box is a <label>, so tapping anywhere on it opens the file picker. */}
        <label
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-12 text-center transition ${
            file
              ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
              : "border-slate-300 hover:border-blue-400 dark:border-slate-700"
          }`}
        >
          <span className="text-4xl" aria-hidden>
            📄
          </span>
          <span className="font-medium break-all">{file ? file.name : "Tap to choose a PDF"}</span>
          <span className="text-sm text-slate-500">
            {file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `Up to ${MAX_MB} MB`}
          </span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            disabled={uploading}
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <button
          type="submit"
          disabled={!file || uploading}
          className="rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? "Reading your PDF…" : "Upload"}
        </button>

        {uploading && (
          <p className="flex items-center justify-center gap-2 text-sm text-slate-500" role="status">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            Extracting text and preparing search. Big PDFs can take a minute.
          </p>
        )}

        {error && (
          <p
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
          >
            {error}
          </p>
        )}
      </form>
    </main>
  );
}

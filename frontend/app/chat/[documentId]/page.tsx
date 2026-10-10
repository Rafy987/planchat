"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";

import AnswerBubble from "@/components/AnswerBubble";
import { askQuestion, getDocument, type DocumentInfo, type Source } from "@/lib/api";

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; answer: string; sources: Source[] }
  | { role: "error"; text: string };

const EXAMPLE_QUESTIONS = ["What flooring is in Room 204?", "Which rooms have carpet tile?"];

export default function ChatPage({ params }: PageProps<"/chat/[documentId]">) {
  // In Next.js 16, page params arrive as a Promise; use() unwraps it.
  const { documentId } = use(params);

  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load the file name and page count for the header.
  useEffect(() => {
    getDocument(documentId)
      .then(setDoc)
      .catch((e: Error) => setLoadError(e.message));
  }, [documentId]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || thinking) return;
    setQuestion("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setThinking(true);
    try {
      const result = await askQuestion(documentId, q);
      setMessages((m) => [...m, { role: "assistant", answer: result.answer, sources: result.sources }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: (e as Error).message }]);
    } finally {
      setThinking(false);
    }
  }

  if (loadError) {
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
        <p className="text-lg font-semibold">{loadError}</p>
        <Link href="/" className="rounded-xl bg-blue-600 px-4 py-2 font-semibold text-white">
          Upload a PDF
        </Link>
      </main>
    );
  }

  return (
    // h-dvh = the real visible screen height on phones (the address bar is excluded).
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col">
      <header className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <Link
          href="/"
          aria-label="Upload another PDF"
          className="rounded-lg px-2 py-1 text-xl hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          ←
        </Link>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{doc?.filename ?? "Loading…"}</p>
          {doc && <p className="text-xs text-slate-500">{doc.page_count} pages</p>}
        </div>
        <Link
          href={`/chat/${encodeURIComponent(documentId)}/flooring`}
          className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-semibold hover:border-blue-400 dark:border-slate-700"
        >
          Flooring
        </Link>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="mt-8 text-center text-slate-500">
            <p>Ask anything about this document.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => send(example)}
                  className="rounded-full border border-slate-300 px-3 py-1.5 text-sm hover:border-blue-400 dark:border-slate-700"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, i) => {
          if (message.role === "user") {
            return (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 whitespace-pre-wrap text-white">
                  {message.text}
                </p>
              </div>
            );
          }
          if (message.role === "error") {
            return (
              <p
                key={i}
                role="alert"
                className="max-w-[90%] rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
              >
                {message.text}
              </p>
            );
          }
          return <AnswerBubble key={i} answer={message.answer} sources={message.sources} />;
        })}

        {thinking && (
          <p className="flex items-center gap-2 text-sm text-slate-500" role="status">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            Thinking…
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input stays at the bottom; extra padding clears the iPhone home bar. */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(question);
        }}
        className="flex gap-2 border-t border-slate-200 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-800"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          maxLength={1000}
          aria-label="Your question"
          // text-base (16px) stops iPhones from zooming in when the input is tapped.
          className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-base outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          disabled={!question.trim() || thinking}
          aria-label="Send"
          className="rounded-xl bg-blue-600 px-4 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          →
        </button>
      </form>
    </main>
  );
}

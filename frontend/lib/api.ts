// All calls to the PlanChat backend live here, so pages stay simple.

// NEXT_PUBLIC_ variables are baked into the JavaScript at build time.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type UploadResult = {
  document_id: string;
  filename: string;
  page_count: number;
  chunk_count: number;
  pages_without_text: number[];
};

export type DocumentInfo = {
  document_id: string;
  filename: string;
  page_count: number;
};

export type Source = { page_number: number; text: string };

export type AskResult = {
  answer: string;
  sources: Source[];
  provider: string | null;
  model: string | null;
};

// Turns any failed response into an Error with a message we can show to users.
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new Error("Can't reach the PlanChat server. Is the backend running?");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    // FastAPI sends {"detail": "message"}, or a list of problems for 422 errors.
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Please check your input and try again."
          : `Something went wrong (error ${response.status}).`;
    throw new Error(message);
  }
  return response.json();
}

export function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return request("/documents", { method: "POST", body: form });
}

export function getDocument(documentId: string): Promise<DocumentInfo> {
  return request(`/documents/${encodeURIComponent(documentId)}`);
}

export function askQuestion(documentId: string, question: string): Promise<AskResult> {
  return request("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, question }),
  });
}

export type FlooringItem = {
  code: string;
  category: string;
  product: string;
  manufacturer: string;
  rooms: string[];
  pages: number[];
};

export type FlooringSchedule = {
  document_id: string;
  extracted_at: string | null; // null = not extracted yet
  items: FlooringItem[];
  warnings: string[];
};

export function getFlooring(documentId: string): Promise<FlooringSchedule> {
  return request(`/documents/${encodeURIComponent(documentId)}/flooring`);
}

// Runs the AI extraction on the server. Can take a minute or two on big plan sets.
export function extractFlooring(documentId: string): Promise<FlooringSchedule> {
  return request(`/documents/${encodeURIComponent(documentId)}/flooring`, { method: "POST" });
}

// A plain link: the browser downloads the CSV file itself.
export function flooringCsvUrl(documentId: string): string {
  return `${API_URL}/documents/${encodeURIComponent(documentId)}/flooring.csv`;
}

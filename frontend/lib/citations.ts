// Splits an answer like "Carpet tile [p. 2]." into pieces, so each [p. N]
// can be shown as a clickable button instead of plain text.

export type AnswerPart = { type: "text"; text: string } | { type: "citation"; page: number };

const CITATION = /\[p\.\s*(\d+)\]/g;

export function splitCitations(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let lastIndex = 0;

  for (const match of answer.matchAll(CITATION)) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", text: answer.slice(lastIndex, match.index) });
    }
    parts.push({ type: "citation", page: Number(match[1]) });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < answer.length) {
    parts.push({ type: "text", text: answer.slice(lastIndex) });
  }
  return parts;
}

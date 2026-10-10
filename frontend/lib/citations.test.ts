import { describe, expect, it } from "vitest";

import { splitCitations } from "./citations";

describe("splitCitations", () => {
  it("turns [p. N] into citation parts between text parts", () => {
    expect(splitCitations("Carpet tile [p. 2] by Interface [p. 3].")).toEqual([
      { type: "text", text: "Carpet tile " },
      { type: "citation", page: 2 },
      { type: "text", text: " by Interface " },
      { type: "citation", page: 3 },
      { type: "text", text: "." },
    ]);
  });

  it("keeps an answer without citations as one text part", () => {
    expect(splitCitations("I couldn't find that in the document.")).toEqual([
      { type: "text", text: "I couldn't find that in the document." },
    ]);
  });

  it("handles a citation at the very start and missing space after 'p.'", () => {
    expect(splitCitations("[p.12] Room 204")).toEqual([
      { type: "citation", page: 12 },
      { type: "text", text: " Room 204" },
    ]);
  });

  it("handles citations right next to each other", () => {
    expect(splitCitations("[p. 2][p. 3]")).toEqual([
      { type: "citation", page: 2 },
      { type: "citation", page: 3 },
    ]);
  });

  it("returns nothing for an empty answer", () => {
    expect(splitCitations("")).toEqual([]);
  });
});

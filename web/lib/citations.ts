export type AnswerPart = { type: "text"; value: string } | { type: "cite"; id: string };

// Same shape as the ids in the knowledge base, e.g. [aws-s3-001]
const CITATION = /\[((?:[a-z0-9]+-)+\d{3})\]/gi;

/** Split an answer into plain text and [citation] parts. */
export function splitCitations(text: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    if (match.index > last) parts.push({ type: "text", value: text.slice(last, match.index) });
    parts.push({ type: "cite", id: match[1].toLowerCase() });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ type: "text", value: text.slice(last) });
  return parts;
}

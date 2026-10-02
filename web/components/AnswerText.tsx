import type { ReactNode } from "react";
import { splitCitations } from "@/lib/citations";

const WORD_DELAY_MS = 22;
const MAX_DELAY_MS = 1400; // long answers must not take forever to appear

type Block = { kind: "p"; text: string } | { kind: "ul" | "ol"; items: string[] };

const BULLET = /^\s*-\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

/** Plain-text answers use "- " bullets, "1." steps and blank lines between paragraphs. */
export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "p", text: paragraph.join(" ") });
    paragraph = [];
  };

  for (const line of text.split("\n")) {
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);
    const item = bullet ?? numbered;

    if (item) {
      flush();
      const kind = bullet ? "ul" : "ol";
      const last = blocks[blocks.length - 1];
      if (last && last.kind === kind) last.items.push(item[1]);
      else blocks.push({ kind, items: [item[1]] });
    } else if (!line.trim()) {
      flush();
    } else {
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}

/**
 * Renders an answer: paragraphs and lists, with [citation] tags turned into chips. Words fade in one
 * after another, so a complete reply still reads like it is being written.
 */
export function AnswerText({ text, messageId, baseDelayMs = 0, animate = true }: { text: string; messageId: string; baseDelayMs?: number; animate?: boolean }) {
  let word = 0;
  const delay = () => `${baseDelayMs + Math.min(word * WORD_DELAY_MS, MAX_DELAY_MS)}ms`;
  const fade = animate ? "motion-safe:animate-fade-in" : "";

  const inline = (source: string, key: string): ReactNode[] => {
    const nodes: ReactNode[] = [];
    splitCitations(source).forEach((part, partIndex) => {
      if (part.type === "cite") {
        nodes.push(
          <a
            key={`${key}c${partIndex}`}
            href={`#${messageId}-${part.id}`}
            className={`${fade} mx-0.5 inline-block border border-hairline px-1.5 align-baseline text-[11px] font-bold uppercase leading-5 tracking-machined text-ink transition-colors hover:border-ink hover:bg-ink hover:text-canvas`}
            style={animate ? { animationDelay: delay() } : undefined}
          >
            {part.id}
          </a>,
        );
        return;
      }
      part.value.split(/(\s+)/).forEach((token, tokenIndex) => {
        if (!token) return;
        if (/^\s+$/.test(token)) {
          nodes.push(token);
          return;
        }
        nodes.push(
          <span key={`${key}t${partIndex}-${tokenIndex}`} className={fade} style={animate ? { animationDelay: delay() } : undefined}>
            {token}
          </span>,
        );
        word += 1;
      });
    });
    return nodes;
  };

  return (
    <div className="max-w-prose space-y-4 text-base leading-relaxed text-body-strong">
      {parseBlocks(text).map((block, blockIndex) => {
        const key = `b${blockIndex}`;
        if (block.kind === "p") return <p key={key}>{inline(block.text, key)}</p>;

        const Tag = block.kind;
        return (
          <Tag key={key} className="list-none space-y-2.5">
            {block.items.map((item, itemIndex) => (
              <li key={`${key}i${itemIndex}`} className="flex gap-3">
                {block.kind === "ul" ? (
                  <span aria-hidden className="mt-3 h-px w-3 shrink-0 bg-muted" />
                ) : (
                  <span aria-hidden className="w-5 shrink-0 pt-1 text-xs font-bold tracking-machined text-muted">
                    {String(itemIndex + 1).padStart(2, "0")}
                  </span>
                )}
                <span>{inline(item, `${key}i${itemIndex}`)}</span>
              </li>
            ))}
          </Tag>
        );
      })}
    </div>
  );
}

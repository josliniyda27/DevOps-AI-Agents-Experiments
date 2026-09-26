import type { Source } from "@/lib/types";

export function SourceCard({ source, anchorId, index, animate = true }: { source: Source; anchorId: string; index: number; animate?: boolean }) {
  const score = source.relevance === null ? null : Math.round(source.relevance * 10);

  return (
    <li
      id={anchorId}
      className={`${animate ? "motion-safe:animate-fade-up" : ""} scroll-mt-6 border border-hairline bg-surface-soft p-5 transition-colors target:border-ink`}
      style={animate ? { animationDelay: `${index * 90}ms` } : undefined}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-bold uppercase tracking-machined text-muted">{source.category}</p>
        {score !== null && (
          <div role="img" aria-label={`Relevance ${score} out of 10`} title={`Relevance ${score}/10`} className="flex gap-0.5">
            {Array.from({ length: 10 }, (_, i) => (
              <span key={i} className={`h-2.5 w-[3px] ${i < score ? "bg-ink" : "bg-hairline"}`} />
            ))}
          </div>
        )}
      </div>
      <h3 className="mt-2 text-xl font-bold leading-tight text-ink">{source.topic}</h3>
      <p className="mt-1 text-xs uppercase tracking-machined text-muted">{source.id}</p>
      {source.file && (
        <p className="mt-2 break-all text-xs text-muted" title="Knowledge-base file">
          <span className="sr-only">File: </span>
          {source.file}
        </p>
      )}

      {source.links.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-hairline-strong pt-3">
          {source.links.map((link) => (
            <li key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center justify-between gap-3 text-sm text-body transition-colors hover:text-ink"
              >
                <span className="truncate">{link.title}</span>
                <span aria-hidden className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none">
                  ↗
                </span>
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

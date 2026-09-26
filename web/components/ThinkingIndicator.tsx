export function ThinkingIndicator() {
  return (
    <div role="status" aria-live="polite" className="motion-safe:animate-fade-in max-w-xs py-2">
      <p className="text-xs font-bold uppercase tracking-machined text-muted">Searching the knowledge base</p>
      <div aria-hidden className="relative mt-3 h-px overflow-hidden bg-hairline">
        <div className="absolute inset-y-0 left-0 w-1/3 bg-ink motion-safe:animate-scan" />
      </div>
    </div>
  );
}

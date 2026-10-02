import type { AssistantMessage, Message } from "@/lib/types";
import { AnswerText } from "./AnswerText";
import { SourceCard } from "./SourceCard";

const ROLE_LABEL = "text-xs font-bold uppercase tracking-machined";

function Assistant({ message, onRetry }: { message: AssistantMessage; onRetry: (question: string) => void }) {
  const { status } = message;
  const animate = !!message.fresh;

  if (status === "blocked" || status === "error") {
    return (
      <div className="border-l-2 border-warning pl-5">
        <p className={`${ROLE_LABEL} text-warning`}>{status === "blocked" ? "Request blocked" : "Connection problem"}</p>
        <p className="mt-2 text-base leading-relaxed text-body-strong">{status === "blocked" ? message.reason : message.text}</p>
        {message.retry && (
          <button
            type="button"
            onClick={() => onRetry(message.retry!)}
            className="mt-4 h-10 border border-ink px-5 text-xs font-bold uppercase tracking-machined text-ink transition-colors hover:bg-ink hover:text-canvas"
          >
            Try again
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="border-l-2 border-hairline pl-5">
      <p className={`${ROLE_LABEL} ${status === "refused" ? "text-muted" : "text-ink"}`}>
        {status === "refused" ? "Not in the knowledge base" : "Assistant"}
      </p>
      {message.standaloneQuestion && (
        <p className="mt-2 text-xs uppercase tracking-machined text-muted">
          Understood as <span className="normal-case tracking-normal text-body">&ldquo;{message.standaloneQuestion}&rdquo;</span>
        </p>
      )}
      <div className="mt-2">
        <AnswerText text={message.text} messageId={message.id} animate={animate} />
      </div>

      {message.sources.length > 0 && (
        <section className="mt-8" aria-labelledby={`${message.id}-origin`}>
          <h3 id={`${message.id}-origin`} className={`${ROLE_LABEL} text-muted`}>
            Where this knowledge comes from
          </h3>
          {message.trace && message.trace.knowledge_base && (
            <p className="mt-2 text-sm text-body">
              {message.trace.knowledge_base.replace(/_/g, " ")} · {message.sources.length} of {message.trace.total_entries} entries cited
            </p>
          )}
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {message.sources.map((source, index) => (
              <SourceCard key={source.id} source={source} anchorId={`${message.id}-${source.id}`} index={index} animate={animate} />
            ))}
          </ul>
        </section>
      )}

      {message.knowledgeSummary && message.knowledgeSummary.length > 0 && (
        <section className="mt-8" aria-labelledby={`${message.id}-summary`}>
          <h3 id={`${message.id}-summary`} className={`${ROLE_LABEL} text-muted`}>
            What the knowledge base says
          </h3>
          <div className="mt-3 border-l border-hairline-strong pl-4 text-body">
            <AnswerText
              text={message.knowledgeSummary.map((line) => `- ${line}`).join("\n")}
              messageId={message.id}
              baseDelayMs={500}
              animate={animate}
            />
          </div>
        </section>
      )}

      {message.trace && (
        <p className={`${animate ? "motion-safe:animate-fade-in" : ""} mt-5 text-xs uppercase tracking-machined text-muted`}>
          {message.trace.candidates} candidates found
          {message.trace.reranked ? " · re-ranked" : ""} · {message.trace.selected} used
          {message.trace.verification === "passed" && " · grounding verified"}
          {message.trace.verification === "revised" && " · revised for grounding"}
        </p>
      )}
    </div>
  );
}

export function MessageBubble({ message, onRetry }: { message: Message; onRetry: (question: string) => void }) {
  if (message.role === "user") {
    return (
      <div className={`${message.fresh ? "motion-safe:animate-fade-up" : ""} flex flex-col items-end`}>
        <p className={`${ROLE_LABEL} mb-2 text-muted`}>You</p>
        <p className="max-w-[85%] whitespace-pre-wrap border border-hairline bg-surface-card px-5 py-4 text-base leading-relaxed text-ink">
          {message.text}
        </p>
      </div>
    );
  }

  return (
    <div className={message.fresh ? "motion-safe:animate-fade-up" : ""}>
      <Assistant message={message} onRetry={onRetry} />
    </div>
  );
}

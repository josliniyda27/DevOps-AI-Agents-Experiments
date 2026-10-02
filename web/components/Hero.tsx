const SUGGESTIONS = [
  { label: "AWS Cloud", question: "What is the difference between ECS and EKS?" },
  { label: "Generative AI", question: "How does RAG reduce hallucination?" },
  { label: "DevOps", question: "How does Terraform fit into a CI/CD workflow?" },
];

export function Hero({ onPick }: { onPick: (question: string) => void }) {
  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col px-4 pb-10 pt-12 sm:px-6 sm:pt-20">
      <p className="motion-safe:animate-fade-up text-sm font-bold uppercase tracking-machined text-muted">
        AI · DevOps · AWS
      </p>

      <h1 className="motion-safe:animate-fade-up mt-4 text-5xl font-bold uppercase leading-none tracking-[-0.5px] text-ink [animation-delay:80ms] sm:text-7xl lg:text-[80px]">
        Ask the
        <br />
        knowledge base.
      </h1>

      <p className="motion-safe:animate-fade-up mt-6 max-w-xl text-lg leading-snug text-body [animation-delay:160ms]">
        Answers come only from our curated knowledge base, every claim cited to its source. If it isn&rsquo;t in
        there, the assistant says so.
      </p>

      <ul className="mt-12 grid gap-px border border-hairline bg-hairline sm:grid-cols-3">
        {SUGGESTIONS.map(({ label, question }, index) => (
          <li key={question} className="motion-safe:animate-fade-up bg-surface-soft" style={{ animationDelay: `${260 + index * 90}ms` }}>
            <button
              type="button"
              onClick={() => onPick(question)}
              className="group flex h-full w-full flex-col justify-between gap-8 p-6 text-left transition-colors hover:bg-surface-card"
            >
              <span className="text-xs font-bold uppercase tracking-machined text-muted">{label}</span>
              <span className="flex items-end justify-between gap-4">
                <span className="text-xl leading-snug text-ink">{question}</span>
                <span
                  aria-hidden
                  className="text-xl text-muted transition-all group-hover:translate-x-1 group-hover:text-ink motion-reduce:transition-none"
                >
                  →
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

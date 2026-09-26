"use client";

import { useEffect, useRef, useState } from "react";
import { MAX_QUESTION_CHARS } from "@/lib/constants";

export function Composer({ onSend, busy, placeholder = "Ask about AWS, DevOps or generative AI" }: { onSend: (text: string) => void; busy: boolean; placeholder?: string }) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!busy) field.current?.focus();
  }, [busy]);

  const tooLong = value.length > MAX_QUESTION_CHARS;
  const canSend = value.trim().length > 0 && !tooLong && !busy;

  function submit() {
    if (!canSend) return;
    onSend(value);
    setValue("");
    if (field.current) field.current.style.height = "auto";
  }

  return (
    <div className="shrink-0 border-t border-hairline bg-canvas">
      <form
        className="mx-auto w-full max-w-4xl px-4 pb-4 pt-4 sm:px-6"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="flex gap-3">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            ref={field}
            rows={1}
            value={value}
            placeholder={placeholder}
            onChange={(event) => setValue(event.target.value)}
            onInput={(event) => {
              const el = event.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
            aria-invalid={tooLong}
            className={`thin-scroll min-h-12 flex-1 resize-none border bg-surface-card px-4 py-3 text-base leading-6 text-ink outline-none transition-colors placeholder:text-muted focus:border-ink ${
              tooLong ? "border-warning" : "border-hairline"
            }`}
          />
          <button
            type="submit"
            disabled={!canSend}
            className="h-12 shrink-0 border border-ink px-6 text-sm font-bold uppercase tracking-machined text-ink transition-colors hover:bg-ink hover:text-canvas disabled:cursor-not-allowed disabled:border-hairline disabled:text-muted disabled:hover:bg-transparent disabled:hover:text-muted sm:px-8"
          >
            Send
          </button>
        </div>

        <div className="mt-3 flex items-center justify-between gap-4 text-xs text-muted">
          <p className="hidden sm:block">Enter to send · Shift+Enter for a new line</p>
          <p className="sm:hidden">Answers come only from the knowledge base.</p>
          {value.length > MAX_QUESTION_CHARS * 0.8 && (
            <p className={tooLong ? "font-bold text-warning" : ""} aria-live="polite">
              {value.length} / {MAX_QUESTION_CHARS}
            </p>
          )}
        </div>
      </form>
    </div>
  );
}

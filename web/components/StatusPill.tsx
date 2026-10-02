"use client";

import { useEffect, useState } from "react";
import { checkHealth } from "@/lib/api";

type State = "checking" | "online" | "offline";

const LABEL: Record<State, string> = { checking: "Connecting", online: "Online", offline: "Offline" };
const DOT: Record<State, string> = { checking: "bg-muted", online: "bg-success", offline: "bg-warning" };

export function StatusPill() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const poll = new AbortController();
    const run = async () => setState((await checkHealth(poll.signal)) ? "online" : "offline");
    run();
    const timer = setInterval(run, 30_000);
    return () => {
      poll.abort();
      clearInterval(timer);
    };
  }, []);

  return (
    <span role="status" className="flex items-center gap-2 text-xs font-bold uppercase tracking-machined text-body">
      <span className="relative flex size-2">
        {state === "online" && (
          <span className="absolute inline-flex size-full rounded-full bg-success opacity-60 motion-safe:animate-ping" />
        )}
        <span className={`relative inline-flex size-2 rounded-full ${DOT[state]}`} />
      </span>
      <span className="hidden sm:inline">{LABEL[state]}</span>
      <span className="sr-only sm:hidden">{LABEL[state]}</span>
    </span>
  );
}

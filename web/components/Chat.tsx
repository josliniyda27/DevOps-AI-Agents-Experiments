"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@/hooks/useChat";
import { useIsDesktop } from "@/hooks/useIsDesktop";
import { Composer } from "./Composer";
import { Hero } from "./Hero";
import { MessageBubble } from "./MessageBubble";
import { NavBar } from "./NavBar";
import { Sidebar } from "./Sidebar";
import { ThinkingIndicator } from "./ThinkingIndicator";

export function Chat() {
  const { conversations, activeId, messages, busy, pending, send, newChat, open, remove, clear } = useChat();
  const isDesktop = useIsDesktop();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const empty = messages.length === 0 && !pending;

  // Empty state: start at the top. Otherwise keep the newest message in view.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (empty) {
      el.scrollTop = 0;
      return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [messages.length, pending, empty, activeId]);

  // Escape closes the mobile drawer.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  // The shell clips (overflow-clip) and the scroll areas are `relative`: nothing inside may ever scroll the page itself,
  // even invisible absolutely-positioned text such as sr-only spans. Only the message list and the sidebar scroll.
  return (
    <div className="relative flex h-dvh flex-col overflow-clip bg-canvas">
      <NavBar onMenu={() => setDrawerOpen(true)} menuOpen={drawerOpen} />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          conversations={conversations}
          activeId={activeId}
          open={drawerOpen}
          inert={!isDesktop && !drawerOpen}
          onOpenConversation={open}
          onNewChat={newChat}
          onDelete={remove}
          onClear={clear}
          onClose={() => setDrawerOpen(false)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={scroller} className="thin-scroll relative min-h-0 flex-1 overflow-y-auto">
            {empty ? (
              <Hero onPick={send} />
            ) : (
              <div role="log" aria-live="polite" className="mx-auto w-full max-w-4xl space-y-10 px-4 py-10 sm:px-6">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} onRetry={send} />
                ))}
                {pending && <ThinkingIndicator />}
              </div>
            )}
          </div>

          <Composer onSend={send} busy={busy} placeholder={empty ? undefined : "Ask a follow-up, or something new"} />
        </div>
      </div>
    </div>
  );
}

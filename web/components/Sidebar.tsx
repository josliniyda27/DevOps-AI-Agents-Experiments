"use client";

import { useState } from "react";
import type { Conversation } from "@/lib/conversations";

function when(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(now) - day(date)) / 86_400_000);

  if (diff === 0) return `Today · ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  if (diff === 1) return "Yesterday";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: date.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}

type Props = {
  conversations: Conversation[];
  activeId: string | null;
  open: boolean; // mobile drawer
  inert: boolean;
  onOpenConversation: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
  onClear: () => void;
  onClose: () => void;
};

export function Sidebar({ conversations, activeId, open, inert, onOpenConversation, onNewChat, onDelete, onClear, onClose }: Props) {
  const [confirmingClear, setConfirmingClear] = useState(false);

  return (
    <>
      {open && <div aria-hidden onClick={onClose} className="motion-safe:animate-fade-in fixed inset-0 z-30 bg-black/70 md:hidden" />}

      <aside
        id="conversations"
        aria-label="Saved conversations"
        inert={inert}
        className={`fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-hairline bg-canvas transition-transform duration-300 motion-reduce:transition-none md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pb-3 pt-4 md:pt-4">
          <span className="text-xs font-bold uppercase tracking-machined text-muted md:hidden">Menu</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close conversations"
            className="flex size-10 items-center justify-center text-xl text-body transition-colors hover:text-ink md:hidden"
          >
            ×
          </button>
        </div>

        <div className="px-4 md:pt-4">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="flex h-12 w-full items-center justify-between border border-ink px-4 text-sm font-bold uppercase tracking-machined text-ink transition-colors hover:bg-ink hover:text-canvas"
          >
            New chat
            <span aria-hidden className="text-lg font-normal leading-none">+</span>
          </button>
        </div>

        <div className="mt-6 flex items-baseline justify-between px-4">
          <h2 className="text-xs font-bold uppercase tracking-machined text-muted">Conversations</h2>
          {conversations.length > 0 && <span className="text-xs text-muted">{conversations.length}</span>}
        </div>

        <nav aria-label="Conversation history" className="thin-scroll relative mt-3 min-h-0 flex-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <p className="px-4 text-sm leading-relaxed text-muted">
              Your conversations are saved here, so you can come back and carry on where you left off.
            </p>
          ) : (
            <ul>
              {conversations.map((conversation) => {
                const isActive = conversation.id === activeId;
                return (
                  <li key={conversation.id} className="group relative">
                    <button
                      type="button"
                      aria-current={isActive ? "true" : undefined}
                      onClick={() => {
                        onOpenConversation(conversation.id);
                        onClose();
                      }}
                      className={`flex w-full flex-col gap-1 border-l-2 py-3 pl-4 pr-12 text-left transition-colors ${
                        isActive ? "border-ink bg-surface-soft" : "border-transparent hover:bg-surface-soft"
                      }`}
                    >
                      <span className={`truncate text-sm ${isActive ? "font-normal text-ink" : "text-body"}`}>{conversation.title}</span>
                      <span className="text-xs text-muted">{when(conversation.updatedAt)}</span>
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete conversation: ${conversation.title}`}
                      onClick={() => {
                        if (window.confirm("Delete this conversation? This can't be undone.")) onDelete(conversation.id);
                      }}
                      className="absolute right-1 top-2 flex size-9 items-center justify-center text-lg text-muted transition-colors hover:text-ink focus-visible:opacity-100 max-md:opacity-100 md:opacity-0 md:group-hover:opacity-100"
                    >
                      ×
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        <div className="border-t border-hairline px-4 py-4">
          <p className="text-xs leading-relaxed text-muted">Saved in this browser only. Nothing is stored on the server.</p>
          {conversations.length > 0 &&
            (confirmingClear ? (
              <div className="mt-3 flex items-center gap-4 text-xs font-bold uppercase tracking-machined">
                <button
                  type="button"
                  onClick={() => {
                    onClear();
                    setConfirmingClear(false);
                  }}
                  className="text-warning transition-colors hover:text-ink"
                >
                  Delete all
                </button>
                <button type="button" onClick={() => setConfirmingClear(false)} className="text-body transition-colors hover:text-ink">
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingClear(true)}
                className="mt-3 text-xs font-bold uppercase tracking-machined text-muted transition-colors hover:text-ink"
              >
                Clear all
              </button>
            ))}
        </div>
      </aside>
    </>
  );
}

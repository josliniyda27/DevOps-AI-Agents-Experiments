"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { askQuestion } from "@/lib/api";
import {
  appendMessages, buildHistory, clearAll, removeConversation, selectConversation,
} from "@/lib/conversations";
import { getStore, updateStore, useConversationStore } from "@/lib/conversationStore";
import type { AssistantMessage, ChatResponse, Message } from "@/lib/types";

const newId = () => globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);

function assistantMessage(reply: ChatResponse): AssistantMessage {
  return {
    id: newId(),
    role: "assistant",
    status: reply.status,
    text: reply.answer,
    sources: reply.sources,
    knowledgeSummary: reply.knowledge_summary,
    standaloneQuestion: reply.standalone_question ?? undefined,
    trace: reply.trace ?? undefined,
    reason: reply.reason ?? undefined,
    fresh: true,
  };
}

export function useChat() {
  const store = useConversationStore();
  const [pendingId, setPendingId] = useState<string | null>(null); // the conversation waiting for a reply
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const active = store.conversations.find((c) => c.id === store.activeId) ?? null;

  const send = useCallback(async (raw: string) => {
    const question = raw.trim();
    if (!question || controller.current) return; // ignore empty input and double-sends

    const current = getStore();
    const conversation = current.conversations.find((c) => c.id === current.activeId);
    const conversationId = conversation?.id ?? newId();
    const history = buildHistory(conversation?.messages ?? []); // earlier turns: what "it" and "that" refer to

    const request = new AbortController();
    controller.current = request;
    setPendingId(conversationId);

    const add = (message: Message, activate = false) =>
      updateStore((s) => appendMessages(s, conversationId, [message], { now: Date.now(), activate }));

    add({ id: newId(), role: "user", text: question, fresh: true }, true);

    try {
      add(assistantMessage(await askQuestion(question, history, request.signal)));
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
      add({ id: newId(), role: "assistant", status: "error", text: (error as Error).message, sources: [], retry: question, fresh: true });
    } finally {
      if (controller.current === request) {
        controller.current = null;
        setPendingId(null);
      }
    }
  }, []);

  const abortPending = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setPendingId(null);
  }, []);

  return {
    conversations: store.conversations,
    activeId: store.activeId,
    messages: active?.messages ?? [],
    busy: pendingId !== null,
    pending: pendingId !== null && pendingId === store.activeId, // show the thinking indicator only where it belongs
    send,
    newChat: useCallback(() => updateStore((s) => selectConversation(s, null)), []),
    open: useCallback((id: string) => updateStore((s) => selectConversation(s, id)), []),
    remove: useCallback((id: string) => {
      if (id === pendingId) abortPending();
      updateStore((s) => removeConversation(s, id));
    }, [pendingId, abortPending]),
    clear: useCallback(() => {
      abortPending();
      updateStore(() => clearAll());
    }, [abortPending]),
  };
}

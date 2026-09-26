/**
 * Saved conversations: the pure logic (no React, no browser APIs), so it can be tested on its own.
 * The browser glue that persists it lives in conversationStore.ts.
 */
import type { AssistantMessage, HistoryTurn, Message } from "./types.ts";

export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
};

export type Store = {
  version: 1;
  conversations: Conversation[]; // most recently active first
  activeId: string | null;
};

export const STORAGE_KEY = "knowledge-assistant.conversations.v1";
export const MAX_CONVERSATIONS = 50;
export const MAX_MESSAGES = 200;
export const HISTORY_TURNS = 6; // messages of earlier conversation sent along with a new question
export const EMPTY_STORE: Store = { version: 1, conversations: [], activeId: null };

const TITLE_CHARS = 48;

export function titleFrom(question: string): string {
  const clean = question.replace(/\s+/g, " ").trim();
  if (!clean) return "New chat";
  return clean.length > TITLE_CHARS ? `${clean.slice(0, TITLE_CHARS - 1).trimEnd()}…` : clean;
}

/**
 * The recent conversation the API needs to understand a follow-up. Only question/answer pairs that
 * were actually answered count: blocked, refused and failed exchanges would only confuse it.
 */
export function buildHistory(messages: Message[], limit = HISTORY_TURNS): HistoryTurn[] {
  const turns: HistoryTurn[] = [];
  for (let i = 0; i < messages.length - 1; i++) {
    const question = messages[i];
    const reply = messages[i + 1];
    if (question.role === "user" && reply.role === "assistant" && reply.status === "answered") {
      turns.push({ role: "user", content: question.text }, { role: "assistant", content: reply.text });
    }
  }
  return turns.slice(-limit);
}

function prune(conversations: Conversation[]): Conversation[] {
  return conversations.slice(0, MAX_CONVERSATIONS);
}

/** Add messages to a conversation (creating it if needed) and move it to the top of the list. */
export function appendMessages(
  store: Store,
  conversationId: string,
  messages: Message[],
  options: { now: number; activate?: boolean },
): Store {
  const existing = store.conversations.find((c) => c.id === conversationId);
  const firstQuestion = messages.find((m) => m.role === "user");

  const updated: Conversation = existing
    ? { ...existing, messages: [...existing.messages, ...messages].slice(-MAX_MESSAGES), updatedAt: options.now }
    : {
        id: conversationId,
        title: titleFrom(firstQuestion?.text ?? ""),
        createdAt: options.now,
        updatedAt: options.now,
        messages: messages.slice(-MAX_MESSAGES),
      };

  const conversations = prune([updated, ...store.conversations.filter((c) => c.id !== conversationId)]);
  const activeId = options.activate ? conversationId : store.activeId;
  return { ...store, conversations, activeId: conversations.some((c) => c.id === activeId) ? activeId : null };
}

/** Open a conversation (or, with null, a blank new chat). Messages stop animating when re-opened. */
export function selectConversation(store: Store, id: string | null): Store {
  const conversations = store.conversations.map((c) => ({
    ...c,
    messages: c.messages.map((m) => (m.fresh ? { ...m, fresh: false } : m)),
  }));
  return { ...store, conversations, activeId: id !== null && conversations.some((c) => c.id === id) ? id : null };
}

export function removeConversation(store: Store, id: string): Store {
  return {
    ...store,
    conversations: store.conversations.filter((c) => c.id !== id),
    activeId: store.activeId === id ? null : store.activeId,
  };
}

export function clearAll(): Store {
  return EMPTY_STORE;
}

export function serialize(store: Store): string {
  return JSON.stringify(store, (key, value) => (key === "fresh" ? undefined : value));
}

// ---- reading what was saved: never trust it (older versions, hand edits, corruption)

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const isText = (value: unknown): value is string => typeof value === "string";

function parseMessage(raw: unknown): Message | null {
  if (!isObject(raw) || !isText(raw.id) || !isText(raw.text)) return null;
  if (raw.role === "user") return { id: raw.id, role: "user", text: raw.text };
  if (raw.role !== "assistant" || !isText(raw.status)) return null;

  const message = raw as unknown as AssistantMessage;
  return { ...message, sources: Array.isArray(message.sources) ? message.sources : [], fresh: undefined };
}

export function parseStore(raw: string | null): Store {
  if (!raw) return EMPTY_STORE;
  try {
    const data: unknown = JSON.parse(raw);
    if (!isObject(data) || data.version !== 1 || !Array.isArray(data.conversations)) return EMPTY_STORE;

    const conversations: Conversation[] = [];
    for (const item of data.conversations) {
      if (!isObject(item) || !isText(item.id) || !isText(item.title) || !Array.isArray(item.messages)) continue;
      const messages = item.messages.map(parseMessage).filter((m): m is Message => m !== null);
      if (messages.length === 0) continue;
      conversations.push({
        id: item.id,
        title: item.title,
        createdAt: typeof item.createdAt === "number" ? item.createdAt : 0,
        updatedAt: typeof item.updatedAt === "number" ? item.updatedAt : 0,
        messages: messages.slice(-MAX_MESSAGES),
      });
    }
    const kept = prune(conversations);
    const activeId = isText(data.activeId) && kept.some((c) => c.id === data.activeId) ? data.activeId : null;
    return { version: 1, conversations: kept, activeId };
  } catch {
    return EMPTY_STORE;
  }
}

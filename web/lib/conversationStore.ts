/**
 * Saved conversations in this browser (localStorage), shared with React through useSyncExternalStore.
 * Everything is saved on every change, so nothing is lost if the tab is closed mid-conversation.
 * The server never sees or stores conversations.
 */
import { useSyncExternalStore } from "react";
import { EMPTY_STORE, STORAGE_KEY, parseStore, serialize, type Store } from "./conversations.ts";

let state: Store = EMPTY_STORE;
let loaded = false;
const listeners = new Set<() => void>();

function load() {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    state = parseStore(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    state = EMPTY_STORE; // storage blocked (private mode, policy): conversations then last for this page only
  }
}

export function getStore(): Store {
  load();
  return state;
}

export function updateStore(change: (store: Store) => Store) {
  load();
  state = change(state);
  try {
    window.localStorage.setItem(STORAGE_KEY, serialize(state));
  } catch {
    // Quota exceeded or storage unavailable: keep working in memory.
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void) {
  listeners.add(notify);

  // Another tab changed the saved conversations: take its list, but keep the conversation open in this tab.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    const incoming = parseStore(event.newValue);
    const keepOpen = state.activeId !== null && incoming.conversations.some((c) => c.id === state.activeId);
    state = { ...incoming, activeId: keepOpen ? state.activeId : null };
    notify();
  };
  window.addEventListener("storage", onStorage);

  return () => {
    listeners.delete(notify);
    window.removeEventListener("storage", onStorage);
  };
}

/** The saved conversations. Empty on the server and during hydration, then the real list. */
export function useConversationStore(): Store {
  return useSyncExternalStore(subscribe, getStore, () => EMPTY_STORE);
}

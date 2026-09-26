"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(min-width: 768px)"; // Tailwind's md breakpoint

function subscribe(notify: () => void) {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", notify);
  return () => media.removeEventListener("change", notify);
}

/** True on screens wide enough to show the sidebar permanently. Assumes desktop on the server. */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches, () => true);
}

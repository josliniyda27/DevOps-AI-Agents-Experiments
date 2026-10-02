import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

/**
 * Regression guard. Screen-reader-only text (sr-only) is absolutely positioned. Inside a scroll area that is not
 * `relative`, its containing block is the page, so it escapes the clipping and makes the whole page scrollable:
 * the header scrolls away and a gap opens under the composer. Keep the shell clipping and the scroll areas relative.
 */
const source = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("the app shell clips, so the page itself can never scroll", () => {
  assert.match(source("components/Chat.tsx"), /className="[^"]*\brelative\b[^"]*\bh-dvh\b[^"]*\boverflow-clip\b/);
});

test("scroll areas are their own containing block, so invisible absolutely positioned text stays inside them", () => {
  assert.match(source("components/Chat.tsx"), /className="[^"]*\brelative\b[^"]*\boverflow-y-auto\b/);
  assert.match(source("components/Sidebar.tsx"), /<nav[^>]*className="[^"]*\brelative\b[^"]*\boverflow-y-auto\b/);
});

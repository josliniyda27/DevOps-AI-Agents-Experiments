import assert from "node:assert/strict";
import { test } from "node:test";
import { backendHeaders, configFromEnv, decide, parseBasic, safeEqual, type GateConfig } from "./gate.ts";

const basic = (user: string, password: string) => `Basic ${Buffer.from(`${user}:${password}`).toString("base64")}`;
const config = (over: Partial<GateConfig> = {}): GateConfig => ({ user: "team", password: "s3cret", secret: "", requireLogin: false, ...over });

test("configuration comes from the environment, and Vercel makes a login mandatory", () => {
  assert.deepEqual(configFromEnv({}), { user: "", password: "", secret: "", requireLogin: false });
  assert.equal(configFromEnv({ VERCEL: "1" }).requireLogin, true);
  assert.equal(configFromEnv({ REQUIRE_LOGIN: "1" }).requireLogin, true);
  assert.equal(configFromEnv({ BASIC_AUTH_USER: "a", BASIC_AUTH_PASSWORD: "b", API_SHARED_SECRET: "c" }).secret, "c");
});

test("without a login configured the site is open for local development", () => {
  assert.equal(decide(null, config({ user: "", password: "" })), "open");
});

test("but where a login is required, a missing one refuses to start rather than opening the site", () => {
  assert.equal(decide(null, config({ user: "", password: "", requireLogin: true })), "misconfigured");
  assert.equal(decide(basic("", ""), config({ password: "", requireLogin: true })), "misconfigured");
});

test("the right user and password are allowed", () => {
  assert.equal(decide(basic("team", "s3cret"), config()), "allowed");
});

test("anything else is denied", () => {
  for (const header of [null, "", "Basic", "Basic !!!not-base64", "Bearer abc", basic("team", "wrong"), basic("other", "s3cret"), basic("", ""), `Basic ${Buffer.from("no-colon").toString("base64")}`]) {
    assert.equal(decide(header, config()), "denied", String(header));
  }
});

test("a password may contain colons and non-ASCII characters", () => {
  assert.equal(decide(basic("team", "a:b:c"), config({ password: "a:b:c" })), "allowed");
  assert.equal(decide(basic("team", "pässwörd✓"), config({ password: "pässwörd✓" })), "allowed");
  assert.deepEqual(parseBasic(basic("u", "p:q")), { user: "u", password: "p:q" });
});

test("comparison is exact, including different lengths and prefixes", () => {
  assert.equal(safeEqual("abc", "abc"), true);
  assert.equal(safeEqual("abc", "abd"), false);
  assert.equal(safeEqual("abc", "abcd"), false);
  assert.equal(safeEqual("", "a"), false);
});

test("the backend receives our secret, never one the browser sent, and never the site password", () => {
  const incoming = new Headers({ "content-type": "application/json", "x-api-secret": "forged", authorization: basic("team", "s3cret") });

  const forwarded = backendHeaders(incoming, "real-secret");
  assert.equal(forwarded.get("x-api-secret"), "real-secret");
  assert.equal(forwarded.get("authorization"), null);
  assert.equal(forwarded.get("content-type"), "application/json");
  assert.equal(incoming.get("x-api-secret"), "forged"); // the original request is left alone
});

test("with no secret configured a forged header is still removed", () => {
  const forwarded = backendHeaders(new Headers({ "x-api-secret": "forged" }), "");
  assert.equal(forwarded.get("x-api-secret"), null);
});

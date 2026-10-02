/**
 * The site's login, and the header that lets only the website call the backend.
 * Pure logic with no Next.js or browser APIs, so it can be tested on its own; proxy.ts applies it.
 */
export type GateConfig = { user: string; password: string; secret: string; requireLogin: boolean };
export type Verdict = "open" | "allowed" | "denied" | "misconfigured";

export function configFromEnv(env: Record<string, string | undefined>): GateConfig {
  return {
    user: env.BASIC_AUTH_USER ?? "",
    password: env.BASIC_AUTH_PASSWORD ?? "",
    secret: env.API_SHARED_SECRET ?? "",
    // On Vercel, or when asked to, a missing login is an error and never an open site.
    requireLogin: env.REQUIRE_LOGIN === "1" || Boolean(env.VERCEL),
  };
}

/** Compares without stopping at the first difference, so timing does not reveal how much matched. */
export function safeEqual(a: string, b: string): boolean {
  let diff = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let i = 0; i < length; i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export function parseBasic(header: string | null): { user: string; password: string } | null {
  if (!header) return null;
  const [scheme, encoded] = header.trim().split(/\s+/);
  if (scheme?.toLowerCase() !== "basic" || !encoded) return null;
  try {
    const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    const decoded = new TextDecoder().decode(bytes); // passwords may not be plain ASCII
    const colon = decoded.indexOf(":"); // the password may itself contain ":"
    return colon < 0 ? null : { user: decoded.slice(0, colon), password: decoded.slice(colon + 1) };
  } catch {
    return null;
  }
}

export function decide(authorization: string | null, config: GateConfig): Verdict {
  if (config.user === "" || config.password === "") return config.requireLogin ? "misconfigured" : "open";

  const given = parseBasic(authorization);
  if (!given) return "denied";
  const userMatches = safeEqual(given.user, config.user);
  const passwordMatches = safeEqual(given.password, config.password);
  return userMatches && passwordMatches ? "allowed" : "denied"; // both compared, always
}

/** Headers for the request forwarded to the backend: the shared secret in, whatever the browser claimed out. */
export function backendHeaders(incoming: Headers, secret: string): Headers {
  const headers = new Headers(incoming);
  headers.delete("x-api-secret"); // never trust a value sent by the browser
  headers.delete("authorization"); // the site password is for the site, not for the backend
  if (secret) headers.set("x-api-secret", secret);
  return headers;
}

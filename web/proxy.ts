import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { backendHeaders, configFromEnv, decide } from "./lib/gate";

/**
 * Runs before every request (not used for the static export in web/Dockerfile, where Caddy does this job):
 *  1. the whole site sits behind a login (BASIC_AUTH_USER / BASIC_AUTH_PASSWORD);
 *  2. calls to /api/* carry API_SHARED_SECRET, which is what lets the backend refuse everyone else.
 */
export function proxy(request: NextRequest) {
  const config = configFromEnv(process.env);
  const verdict = decide(request.headers.get("authorization"), config);

  if (verdict === "misconfigured") {
    return new NextResponse("The login is not configured on this deployment.", { status: 500 });
  }
  if (verdict === "denied") {
    return new NextResponse("Sign in to continue.", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="Knowledge Assistant", charset="UTF-8"' },
    });
  }

  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.next({ request: { headers: backendHeaders(request.headers, config.secret) } });
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };

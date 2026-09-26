import type { NextConfig } from "next";

// Development and `next start`: the browser only talks to Next, which proxies /api/* to the Python API.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

// Production build (STATIC_EXPORT=1, used by web/Dockerfile): plain static files in ./out. There is no Node server
// then, so the proxy is done by the web server in front (Caddy) and no rewrite is needed.
const nextConfig: NextConfig = process.env.STATIC_EXPORT
  ? { output: "export" }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
      },
    };

export default nextConfig;

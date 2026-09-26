# Knowledge Assistant - web UI

Next.js (App Router) + Tailwind CSS v4. Dark, sharp-cornered, uppercase-display styling; animations are Tailwind
`animate-*` utilities defined in `app/globals.css` and disabled for users who prefer reduced motion.

The browser only talks to Next. `next.config.ts` proxies `/api/*` to the Python API (default `http://127.0.0.1:8000`,
override with `API_URL`), so there is no CORS setup and the OpenAI key never reaches the browser.

```bash
# terminal 1 (repo root): the API
.venv/bin/uvicorn src.api:app --port 8000

# terminal 2: the UI
cd web && npm install && npm run dev      # http://localhost:3000
```

| Path | Purpose |
|---|---|
| `app/globals.css` | Design tokens (`@theme`) and keyframes |
| `components/` | `Chat`, `Hero`, `MessageBubble`, `AnswerText` (citation chips + word fade-in), `SourceCard`, `Composer`, ... |
| `hooks/useChat.ts` | Chat state, request cancelling, retry |
| `lib/api.ts` | Calls to `/api/chat` and `/api/health` |

`npm run build` and `npm run lint` must pass before merging.

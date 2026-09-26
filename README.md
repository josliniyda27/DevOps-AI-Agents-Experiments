# Experiments - RAG knowledge-base chatbot

Answers questions about AI/GenAI, DevOps and AWS strictly from our knowledge base.

```
question -> input guardrail -> vector search (Chroma) -> merge into entries -> LLM re-rank -> grounding gate -> LLM -> output guardrail -> answer
```

## Layout

| Path | What it is |
|---|---|
| `data/knowledge_base_v1/` | The knowledge base (JSON, one topic per file) |
| `src/knowledge_base/` | Loader + validator (normalises and de-duplicates entries) |
| `src/retrieval/` | Chunking, embeddings, Chroma store, semantic search (`retriever.py`) |
| `src/guardrails/` | Input/output guardrails for the chain (`guardrail.py` is the earlier DevOps-agent one, unused) |
| `src/generation/` | System prompt, context builder, LLM factory, the RAG chain |
| `src/config.py` | All settings, read from environment / `.env` |
| `src/cli.py` | Command-line chatbot |
| `src/api.py` | HTTP API (FastAPI) used by the web UI |
| `kb_agents/` | Agentic workflow (LangGraph) that grows the knowledge base; runs separately from the chatbot |
| `web/` | Next.js + Tailwind chat UI (see `web/README.md`) |
| `tests/` | `pytest` suite (runs offline; no API key needed) |
| `docs/` | Notes for the knowledge base and the original guardrail |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add your OPENAI_API_KEY (and OPENAI_BASE_URL if you use a gateway)
python -m src.retrieval.ingest  # build the Chroma store (first run downloads a ~80 MB local embedding model)
```

`.env` is git-ignored. Never commit keys.

## Use

```bash
python -m src.retrieval.search "how do I store files in the cloud?"   # semantic search only, no LLM
python -m src.cli "What is Amazon S3?"                                # full chatbot (needs the API key)
python -m src.cli                                                     # interactive
python -m pytest

# web UI: API in one terminal, UI in another
uvicorn src.api:app --port 8000
cd web && npm install && npm run dev      # http://localhost:3000
```

## Conversation memory

Follow-ups work: after "What is ECS?", "And EKS?" is understood as "What is EKS?". The API rewrites a follow-up into a standalone
question from the recent chat (the history is sanitised and only used for that rewrite; it never reaches the answering prompt),
and the UI shows how it was understood. Conversations are saved in the browser (`localStorage`) and listed in the left sidebar,
so they survive closing the tab; the server stores nothing.

## Deploying

`docker compose up -d --build` runs the whole thing on any Linux server (Docker, Compose and Caddy, with a password and
automatic HTTPS). See `docs/deploy.md`.

## Knowledge base

`python -m src.knowledge_base.workflow` validates the knowledge base, syncs its indexes and rebuilds the vector store.
`python -m kb_agents run --domain aws|devops|genai` researches, writes, fact-checks and stages new entries.
See `docs/knowledge_base.md`.

## How retrieval works

1. **Vector search** fetches `CANDIDATES` (20) chunks from Chroma.
2. **Merge**: chunks are grouped back into whole knowledge-base entries, so one topic cannot fill every slot.
3. **Re-rank**: a small LLM judge (`RERANK_MODEL`) scores each entry 0-10 for how well it answers *this* question.
   Entries below `RERANK_MIN_SCORE` are dropped and the best `TOP_K` are kept. If the judge fails, the vector order is used.
4. The model receives the entries as plain notes (not JSON fields) under a strict system prompt
   (`src/generation/prompts.py`): answer only from the documents, cite ids, plain text.

5. Every answer also carries a **knowledge summary** (an overview of what the retrieved documents contain), written by
   the model under the same rules and guardrails as the answer. Where the knowledge comes from (knowledge base, entry,
   source file, official links) is filled in by the app from retrieval metadata, never by the model.

Definition questions ("What is X exactly?", or just a topic name) get a complete definition: what it is, what it provides,
how it works and how it is used.

Set `RERANKER=none` to disable step 3. `VERIFY_ANSWERS=true` adds an optional answer audit; it is off by default
because an A/B test showed no reduction in unsupported claims.

## Known limits

- On comparison and "which should I choose" questions the model sometimes adds judgements the documents do not make
  (for example "ideal for..."). Factual and explanatory questions were clean in our checks.
- The knowledge base is small (62 entries); anything outside it is refused.

## How the guardrails work

- **Input:** blocks prompt injection, credentials/secrets and harmful requests; masks emails, SSNs and card numbers.
- **Scope:** decided by retrieval, not keywords. If nothing in the knowledge base is similar enough (`MIN_SCORE`), the bot refuses **without calling the LLM**.
- **Output:** redacts secrets, replaces answers that repeat the system prompt, removes citations of documents that were not retrieved.

Regex-based injection detection cannot be complete (e.g. an on-topic question with an injected instruction in another language can still reach the model). The system prompt and output guard are the backstop.

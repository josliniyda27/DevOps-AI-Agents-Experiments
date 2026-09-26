"""
HTTP API for the web UI.

    uvicorn src.api:app --port 8000

GET  /api/health
POST /api/chat   {"question": "..."}  ->  {"status", "answer", "sources", "reason"}

status: "answered" | "refused" (nothing relevant in the knowledge base) | "blocked" (input guardrail)
"""

import hmac
import logging
import re
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.config import get_settings
from src.generation.chain import build_rag_pipeline
from src.generation.prompts import NO_ANSWER
from src.guardrails import GuardrailViolation
from src.guardrails.input_guards import MAX_INPUT_CHARS
from src.knowledge_base import KnowledgeBaseLoader

logger = logging.getLogger("rag.api")

_CITATION = re.compile(r"\[((?:[a-z0-9]+-)+\d{3})\]", re.IGNORECASE)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    # Sizes are enforced by the input guardrail (which explains itself); this only bounds the payload.
    question: str = Field(max_length=MAX_INPUT_CHARS * 4)
    # Recent conversation, used only to understand follow-ups. Untrusted: sanitised server-side.
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)


class SourceLink(BaseModel):
    title: str
    url: str


class Source(BaseModel):
    id: str
    topic: str
    category: str
    links: list[SourceLink]
    file: str = ""                    # the knowledge-base file the entry comes from
    relevance: float | None = None    # re-ranker score scaled to 0-1; None if results were not re-ranked


class Trace(BaseModel):
    """How the answer was found: candidates from the vector search, and how many the model was given."""
    candidates: int
    selected: int
    reranked: bool
    verification: str = "skipped"   # passed | revised | unverified | skipped
    knowledge_base: str = ""        # e.g. "knowledge_base_v1"
    total_entries: int = 0


class ChatResponse(BaseModel):
    status: str
    answer: str
    sources: list[Source] = []
    knowledge_summary: list[str] = []   # the model's overview of what the retrieved documents contain
    standalone_question: str | None = None   # how a follow-up was understood; None when it needed no rewriting
    trace: Trace | None = None
    reason: str | None = None


def _links(entry: dict) -> list[SourceLink]:
    links = [SourceLink(title=e.get("title") or e["url"], url=e["url"])
             for e in entry.get("official_evidence", []) if isinstance(e, dict) and e.get("url")]
    links += [SourceLink(title=url, url=url) for url in entry.get("official_links", [])]
    return links


def cited_sources(answer: str, docs: list, entries: dict[str, dict]) -> list[Source]:
    """
    The entries the answer cites, in order of first citation. Only entries the model was actually
    given can be sources, whatever the answer claims.
    """
    given = {doc.metadata["id"].lower(): doc for doc in docs}
    sources, seen = [], set()
    for match in _CITATION.finditer(answer):
        entry_id = match.group(1).lower()
        if entry_id in given and entry_id in entries and entry_id not in seen:
            seen.add(entry_id)
            entry = entries[entry_id]
            sources.append(Source(
                id=entry["id"], topic=entry["topic"], category=entry["category"],
                links=_links(entry), file=entry.get("source", ""), relevance=given[entry_id].metadata.get("relevance"),
            ))
    return sources


def _trace(docs: list, verification: str, total_entries: int) -> Trace | None:
    if not docs:
        return None
    meta = docs[0].metadata
    return Trace(candidates=meta.get("candidates", len(docs)), selected=len(docs),
                 reranked=bool(meta.get("reranked")), verification=verification,
                 knowledge_base=get_settings().data_dir.name, total_entries=total_entries)


def create_app(pipeline=None, shared_secret: str | None = None) -> FastAPI:
    """
    `pipeline` (question -> {"answer", "docs"}) can be injected in tests; by default the real one is built at startup.
    `shared_secret` defaults to API_SHARED_SECRET; when non-empty, /api/chat requires it in the X-Api-Secret header.
    """
    state: dict = {}
    secret = get_settings().api_shared_secret if shared_secret is None else shared_secret

    def require_secret(x_api_secret: str | None = Header(default=None)) -> None:
        if secret and not hmac.compare_digest((x_api_secret or "").encode(), secret.encode()):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        entries = KnowledgeBaseLoader(get_settings().data_dir).load_entries().entries
        state["entries"] = {e["id"].lower(): e for e in entries}
        state["pipeline"] = pipeline or build_rag_pipeline()
        yield

    app = FastAPI(title="Knowledge Assistant API", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "entries": len(state["entries"]), "llm_model": get_settings().llm_model}

    @app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_secret)])
    def chat(request: ChatRequest):
        try:
            result = state["pipeline"].invoke({
                "question": request.question,
                "history": [turn.model_dump() for turn in request.history],
            })
        except GuardrailViolation as blocked:
            return ChatResponse(status="blocked", answer="", reason=blocked.reason)
        except Exception:
            logger.exception("Chat request failed")
            raise HTTPException(status_code=502, detail="The assistant could not complete the request. Please try again.")

        answer, docs = result["answer"], result["docs"]
        standalone = result.get("standalone_question")
        rewritten = standalone if standalone and standalone != result.get("question") else None

        if answer.strip() == NO_ANSWER:
            return ChatResponse(status="refused", answer=answer, standalone_question=rewritten)
        return ChatResponse(
            status="answered", answer=answer, standalone_question=rewritten,
            sources=cited_sources(answer, docs, state["entries"]),
            knowledge_summary=result.get("knowledge_summary", []),
            trace=_trace(docs, result.get("verification", "skipped"), len(state["entries"])),
        )

    return app


app = create_app()

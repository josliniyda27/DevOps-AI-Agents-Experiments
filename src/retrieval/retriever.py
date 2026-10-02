"""
Retrieval over the Chroma knowledge base.

  search()    - semantic search: embed the query with the model used at ingestion and return the
                nearest chunks by cosine similarity.
  retrieve()  - what the chatbot uses: a wide search, chunks merged back into whole entries, then
                re-ranked for relevance to the question (see rerank.py).
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import Runnable, RunnableLambda

from src.config import Settings, get_settings
from src.knowledge_base import KnowledgeBaseLoader
from src.retrieval.embeddings import embedding_label
from src.retrieval.passages import entry_to_passage
from src.retrieval.rerank import Candidate, Reranker, get_reranker
from src.retrieval.vector_store import get_vectorstore

logger = logging.getLogger("rag.retrieval")


@dataclass(frozen=True)
class SearchResult:
    document: Document
    score: float  # cosine similarity, 0-1 (higher is more similar)


def load_store(settings: Settings | None = None, embeddings: Embeddings | None = None) -> Chroma:
    """Open the persisted store, failing clearly if it is missing or was built with another model."""
    settings = settings or get_settings()
    store = get_vectorstore(settings, embeddings)

    if store._collection.count() == 0:
        raise RuntimeError("The vector store is empty. Build it first with: python -m src.retrieval.ingest")

    built_with = (store._collection.metadata or {}).get("embedding_model")
    current = embedding_label(settings)
    if built_with and built_with != current:
        raise RuntimeError(
            f"The store was built with '{built_with}' but the current setting is '{current}'. "
            "Re-run: python -m src.retrieval.ingest"
        )
    return store


@lru_cache(maxsize=1)
def _default_store() -> Chroma:
    return load_store()


def search(
    query: str,
    k: int | None = None,
    category: str | None = None,
    min_score: float | None = None,
    settings: Settings | None = None,
    store: Chroma | None = None,
) -> list[SearchResult]:
    """
    Return up to `k` chunks most similar to `query`, best first.

    category  - only search chunks in this category (e.g. "AWS Cloud")
    min_score - drop chunks scoring below this cosine similarity
    Defaults for k and min_score come from settings (TOP_K, MIN_SCORE).
    """
    use_cached_store = store is None and settings is None
    settings = settings or get_settings()
    k = settings.top_k if k is None else k
    min_score = settings.min_score if min_score is None else min_score

    if k < 1:
        raise ValueError("k must be at least 1")
    if not query or not query.strip():
        return []

    if store is None:
        store = _default_store() if use_cached_store else load_store(settings)

    hits = store.similarity_search_with_score(
        query.strip(),
        k=k,
        filter={"category": category} if category else None,
    )

    results = []
    for document, distance in hits:
        score = round(1.0 - distance, 4)  # the collection uses cosine distance
        if score >= min_score:
            results.append(SearchResult(Document(page_content=document.page_content,
                                                 metadata={**document.metadata, "score": score}), score))
    return results


@dataclass(frozen=True)
class EntryHit:
    entry: dict
    vector_score: float          # best cosine similarity among the entry's chunks (0-1)
    rerank_score: int | None     # 0-10 from the re-ranker; None if the results were not re-ranked

    @property
    def relevance(self) -> float | None:
        """Re-ranker score scaled to 0-1, or None when not re-ranked."""
        return None if self.rerank_score is None else self.rerank_score / 10


@dataclass(frozen=True)
class Retrieval:
    hits: list[EntryHit]
    candidates: int    # distinct entries found by the vector search
    reranked: bool


@lru_cache(maxsize=2)
def _kb_entries(data_dir: str) -> dict[str, dict]:
    return {e["id"]: e for e in KnowledgeBaseLoader(data_dir).load_entries().entries}


def retrieve(
    query: str,
    k: int | None = None,
    category: str | None = None,
    min_score: float | None = None,
    settings: Settings | None = None,
    store: Chroma | None = None,
    reranker: Reranker | None = None,
    entries: dict[str, dict] | None = None,
) -> Retrieval:
    """
    1. Vector search for `candidate_pool` chunks (chunks below `min_score` similarity are dropped).
    2. Merge chunks into their entries, so one topic cannot fill every slot.
    3. Re-rank the entries for relevance to the question and drop those below `rerank_min_score`.
       If the re-ranker fails, fall back to vector order rather than failing the request.
    4. Return the best `k` entries.
    """
    caller_settings = settings
    settings = settings or get_settings()
    k = settings.top_k if k is None else k
    if k < 1:
        raise ValueError("k must be at least 1")

    entries = entries if entries is not None else _kb_entries(str(settings.data_dir))
    reranker = reranker if reranker is not None else get_reranker(settings)

    chunks = search(query, k=settings.candidate_pool, category=category, min_score=min_score,
                    settings=caller_settings, store=store)

    best: dict[str, float] = {}
    for chunk in chunks:
        entry_id = chunk.document.metadata["id"]
        if entry_id in entries:
            best[entry_id] = max(best.get(entry_id, 0.0), chunk.score)
    ordered = sorted(best.items(), key=lambda item: item[1], reverse=True)

    scores: dict[str, int] = {}
    if reranker.active and ordered:
        candidates = [Candidate(i, entry_to_passage(entries[i]), score) for i, score in ordered]
        try:
            scores = reranker.rerank(query, candidates)
        except Exception:
            logger.warning("Re-ranking failed; falling back to vector order", exc_info=True)

    if scores:
        hits = [EntryHit(entries[i], vector, scores.get(i, 0)) for i, vector in ordered]
        hits = [h for h in hits if h.rerank_score >= settings.rerank_min_score]
        hits.sort(key=lambda h: (h.rerank_score, h.vector_score), reverse=True)
    else:
        hits = [EntryHit(entries[i], vector, None) for i, vector in ordered]

    return Retrieval(hits[:k], candidates=len(ordered), reranked=bool(scores))


def hit_to_document(hit: EntryHit, retrieval: Retrieval) -> Document:
    entry = hit.entry
    return Document(
        page_content=entry_to_passage(entry),
        metadata={
            "id": entry["id"],
            "topic": entry["topic"],
            "category": entry["category"],
            "source": entry.get("source", ""),
            "vector_score": round(hit.vector_score, 4),
            "rerank_score": hit.rerank_score,
            "relevance": hit.relevance,
            "reranked": retrieval.reranked,
            "candidates": retrieval.candidates,
        },
    )


def get_retriever(
    k: int | None = None,
    category: str | None = None,
    min_score: float | None = None,
    settings: Settings | None = None,
    store: Chroma | None = None,
    reranker: Reranker | None = None,
) -> Runnable:
    """
    A LangChain runnable: question -> list[Document], one whole entry per document, best first.
    Drop-in for `retriever | format_docs_to_xml` in the generation chain.
    """
    def _retrieve(query: str) -> list[Document]:
        retrieval = retrieve(query, k, category, min_score, settings, store, reranker)
        return [hit_to_document(hit, retrieval) for hit in retrieval.hits]

    return RunnableLambda(_retrieve, name="kb_retriever")

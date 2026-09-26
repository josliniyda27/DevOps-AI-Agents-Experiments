import dataclasses

import pytest
from langchain_core.runnables import RunnableLambda

from src.config import get_settings
from src.retrieval.rerank import Candidate, LLMReranker, NoReranker, PassageScore, RerankResult, get_reranker
from src.retrieval.retriever import get_retriever, retrieve


def _candidates(*ids):
    return [Candidate(i, f"text of {i}", 0.5) for i in ids]


def _scorer(scores):
    """A fake LLM scorer: returns the given {id: score} as the judge's structured result."""
    return RunnableLambda(lambda _: RerankResult(scores=[PassageScore(id=i, score=s) for i, s in scores.items()]))


# ---------- the LLM re-ranker ----------

def test_scores_are_clamped_to_0_10_and_unknown_ids_ignored():
    reranker = LLMReranker(_scorer({"a": 15, "b": -3, "ghost": 9}))
    assert reranker.rerank("q", _candidates("a", "b")) == {"a": 10, "b": 0}


def test_a_candidate_the_judge_skipped_counts_as_irrelevant():
    assert LLMReranker(_scorer({"a": 8})).rerank("q", _candidates("a", "b")) == {"a": 8, "b": 0}


def test_a_useless_judge_response_raises_so_callers_can_fall_back():
    with pytest.raises(ValueError):
        LLMReranker(_scorer({"ghost": 9})).rerank("q", _candidates("a"))


def test_the_judge_sees_the_question_and_every_passage_id():
    seen = {}

    def spy(payload):
        seen.update(payload)
        return RerankResult(scores=[PassageScore(id="a", score=5)])

    LLMReranker(RunnableLambda(spy)).rerank("What is S3?", _candidates("a", "b"))
    assert seen["question"] == "What is S3?" and "[a]" in seen["passages"] and "[b]" in seen["passages"]


def test_reranker_factory_validates_its_configuration():
    base = get_settings()
    assert isinstance(get_reranker(dataclasses.replace(base, reranker="none")), NoReranker)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_reranker(dataclasses.replace(base, reranker="llm", openai_api_key=""))
    with pytest.raises(ValueError, match="Unknown RERANKER"):
        get_reranker(dataclasses.replace(base, reranker="magic"))


# ---------- retrieval: merge chunks into entries, then re-rank ----------

class ScriptedReranker:
    """Scores candidates by a function of their vector-rank, so tests can force any ordering."""
    active = True

    def __init__(self, score_of):
        self.score_of, self.seen = score_of, None

    def rerank(self, question, candidates):
        self.seen = list(candidates)
        return {c.id: self.score_of(n, c) for n, c in enumerate(candidates)}


class BrokenReranker:
    active = True

    def rerank(self, question, candidates):
        raise RuntimeError("judge unavailable")


def _retrieve(fake_store, reranker, **kw):
    settings = dataclasses.replace(get_settings(), candidate_pool=30, rerank_min_score=5)
    return retrieve("How do I deploy containers?", min_score=-1, settings=settings, store=fake_store, reranker=reranker, **kw)


def test_chunks_are_merged_so_an_entry_appears_once(fake_store):
    hits = _retrieve(fake_store, NoReranker(), k=30).hits
    ids = [h.entry["id"] for h in hits]
    assert len(ids) == len(set(ids)) and len(ids) > 1


def test_the_reranker_receives_whole_entries_as_prose_not_json_labels(fake_store):
    reranker = ScriptedReranker(lambda n, c: 9)
    _retrieve(fake_store, reranker)
    text = reranker.seen[0].text
    assert "Core ideas" in text or "Example uses" in text or "In practice" in text
    for label in ("key_concepts", "devops_application", "official_evidence", "Key concepts:", "Workflow:"):
        assert label not in text


def test_reranking_can_promote_an_entry_the_vector_search_ranked_low(fake_store):
    n_candidates = _retrieve(fake_store, NoReranker(), k=30).candidates
    last = n_candidates - 1
    retrieval = _retrieve(fake_store, ScriptedReranker(lambda n, c: 10 if n == last else 6), k=3)

    assert retrieval.reranked and retrieval.hits[0].rerank_score == 10
    assert retrieval.hits[0].vector_score < retrieval.hits[1].vector_score          # low on similarity, top on relevance


def test_entries_below_the_relevance_threshold_are_dropped(fake_store):
    retrieval = _retrieve(fake_store, ScriptedReranker(lambda n, c: 9 if n < 2 else 4), k=10)
    assert len(retrieval.hits) == 2 and all(h.rerank_score == 9 for h in retrieval.hits)


def test_when_the_judge_finds_nothing_relevant_nothing_is_returned(fake_store):
    assert _retrieve(fake_store, ScriptedReranker(lambda n, c: 1), k=4).hits == []


def test_a_failing_reranker_falls_back_to_vector_order_instead_of_failing(fake_store):
    fallback = _retrieve(fake_store, BrokenReranker(), k=4)
    plain = _retrieve(fake_store, NoReranker(), k=4)

    assert not fallback.reranked and fallback.hits and all(h.rerank_score is None for h in fallback.hits)
    assert [h.entry["id"] for h in fallback.hits] == [h.entry["id"] for h in plain.hits]


def test_retriever_documents_carry_whole_entries_and_relevance_metadata(fake_store):
    settings = dataclasses.replace(get_settings(), candidate_pool=30)
    docs = get_retriever(k=3, min_score=-1, settings=settings, store=fake_store,
                         reranker=ScriptedReranker(lambda n, c: 8)).invoke("anything")
    meta = docs[0].metadata
    assert len(docs) == 3 and meta["reranked"] is True and meta["relevance"] == 0.8 and meta["candidates"] >= 3
    assert docs[0].page_content.startswith(meta["topic"])

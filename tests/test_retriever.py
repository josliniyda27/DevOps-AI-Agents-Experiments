import dataclasses
from pathlib import Path

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from src.config import get_settings
from src.retrieval.ingest import ingest
from src.retrieval.retriever import get_retriever, load_store, search
from src.retrieval.vector_store import get_vectorstore

LOCAL_MODEL = Path.home() / ".cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/model.onnx"


def _settings(tmp_path):
    return dataclasses.replace(get_settings(), chroma_dir=tmp_path / "chroma")


def _some_chunk(store) -> Document:
    got = store.get(ids=["aws-s3-001::0"])
    return Document(page_content=got["documents"][0], metadata=got["metadatas"][0])


def test_exact_text_finds_its_own_chunk(fake_store):
    chunk = _some_chunk(fake_store)
    top = search(chunk.page_content, store=fake_store)[0]
    assert top.document.metadata["chunk_id"] == "aws-s3-001::0"
    assert top.score == pytest.approx(1.0, abs=1e-3)


def test_results_respect_k_and_are_sorted(fake_store):
    query = _some_chunk(fake_store).page_content
    results = search(query, k=5, min_score=-1, store=fake_store)
    assert len(results) == 5
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_category_filter_only_returns_that_category(fake_store):
    query = _some_chunk(fake_store).page_content
    results = search(query, k=10, min_score=-1, category="DevOps", store=fake_store)
    assert results and all(r.document.metadata["category"] == "DevOps" for r in results)


def test_min_score_drops_weak_matches(fake_store):
    query = _some_chunk(fake_store).page_content
    strict = search(query, k=10, min_score=0.99, store=fake_store)
    assert [r.document.metadata["chunk_id"] for r in strict] == ["aws-s3-001::0"]


def test_blank_query_returns_nothing_and_bad_k_is_rejected(fake_store):
    assert search("   ", store=fake_store) == []
    with pytest.raises(ValueError):
        search("anything", k=0, store=fake_store)


def test_retriever_returns_documents_with_scores(fake_store):
    query = _some_chunk(fake_store).page_content
    docs = get_retriever(k=2, min_score=-1, store=fake_store).invoke(query)
    assert len(docs) == 2
    assert all(isinstance(d, Document) and "vector_score" in d.metadata for d in docs)


def test_empty_store_gives_a_clear_error(tmp_path):
    with pytest.raises(RuntimeError, match="python -m src.retrieval.ingest"):
        load_store(_settings(tmp_path), DeterministicFakeEmbedding(size=64))


def test_store_built_with_another_model_is_rejected(tmp_path):
    settings = _settings(tmp_path)
    embeddings = DeterministicFakeEmbedding(size=64)
    ingest(settings, embeddings)

    switched = dataclasses.replace(settings, embedding_provider="openai", embedding_model="some-other-model")
    with pytest.raises(RuntimeError, match="built with"):
        load_store(switched, embeddings)


@pytest.fixture(scope="module")
def real_store(tmp_path_factory, local_embeddings):
    """A store built with the real local embedding model."""
    settings = _settings(tmp_path_factory.mktemp("real"))
    ingest(settings, local_embeddings)
    return get_vectorstore(settings, local_embeddings)


@pytest.mark.skipif(not LOCAL_MODEL.exists(), reason="local embedding model not downloaded yet")
class TestSemanticQuality:
    """Uses the real local model: checks that meaning, not keywords, drives the results."""

    @pytest.mark.parametrize("query, expected_topic", [
        ("how do I store files in the cloud?", "S3"),
        ("what is retrieval augmented generation?", "RAG"),
        ("how to reduce LLM token costs", "Token Cost Optimization"),
        ("container orchestration", "Kubernetes"),
        ("explain few shot prompting", "Few-shot Prompting"),
    ])
    def test_finds_the_right_topic(self, real_store, query, expected_topic):
        topics = [r.document.metadata["topic"] for r in search(query, k=3, store=real_store)]
        assert expected_topic in topics

    @pytest.mark.parametrize("query", ["tell me a movie story", "best chocolate cake recipe", "who won the football world cup"])
    def test_off_topic_questions_find_nothing(self, real_store, query):
        assert search(query, store=real_store) == []

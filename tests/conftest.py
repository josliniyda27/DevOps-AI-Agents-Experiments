import os

# The suite must never call a real LLM: keep the re-ranker and verifier off unless a test injects its own.
os.environ["RERANKER"] = "none"
os.environ["VERIFY_ANSWERS"] = "false"

import dataclasses
import gc
from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from src.config import get_settings
from src.retrieval.ingest import ingest
from src.retrieval.vector_store import get_vectorstore


@pytest.fixture(scope="session")
def fake_store(tmp_path_factory):
    """A real Chroma store built with deterministic (non-semantic) embeddings: tests mechanics, not meaning."""
    settings = dataclasses.replace(get_settings(), chroma_dir=tmp_path_factory.mktemp("fake") / "chroma")
    embeddings = DeterministicFakeEmbedding(size=64)
    ingest(settings, embeddings)
    return get_vectorstore(settings, embeddings)


LOCAL_MODEL = Path.home() / ".cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/model.onnx"


@pytest.fixture(scope="session")
def local_embeddings():
    """One copy of the real local embedding model for the whole run (each copy is an ONNX session with its own threads)."""
    if not LOCAL_MODEL.exists():
        pytest.skip("local embedding model not downloaded yet")
    from src.retrieval.embeddings import LocalEmbeddings

    return LocalEmbeddings()


def pytest_sessionfinish(session, exitstatus):
    """Close Chroma's cached clients before the interpreter shuts down: tearing many of them down at exit can segfault."""
    try:
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
    except Exception:
        pass
    gc.collect()

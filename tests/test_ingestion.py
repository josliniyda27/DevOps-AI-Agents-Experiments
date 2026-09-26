import dataclasses
import json

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from src.config import get_settings
from src.knowledge_base import KnowledgeBaseLoader
from src.retrieval.chunker import chunk_entries
from src.retrieval.ingest import ingest


@pytest.fixture(scope="module")
def report():
    return KnowledgeBaseLoader(get_settings().data_dir).load_entries()


def test_loader_reads_every_entry(report):
    raw_count = 0
    for path in get_settings().data_dir.rglob("*.json"):
        if "indexes" not in path.parts:
            content = json.loads(path.read_text(encoding="utf-8"))
            raw_count += len(content) if isinstance(content, list) else 1

    assert report.invalid == []
    assert len(report.entries) + len(report.duplicates) == raw_count


def test_loader_normalises_course_projects(report):
    entry = next(e for e in report.entries if e["id"] == "cp-aws-chatops-001")
    assert entry["category"] == "Course Projects"
    assert entry["answer"].startswith("An agentic AI demo")


def test_loader_has_unique_ids(report):
    ids = [e["id"] for e in report.entries]
    assert len(ids) == len(set(ids))


def test_chunks_are_self_describing_and_bounded(report):
    docs = chunk_entries(report.entries, chunk_size=500, chunk_overlap=60)
    assert len(docs) > len(report.entries)
    for d in docs:
        assert d.page_content.startswith("Topic: ")
        assert len(d.page_content) < 700
        assert all(isinstance(v, (str, int)) for v in d.metadata.values())  # Chroma-safe metadata
    assert len({d.metadata["chunk_id"] for d in docs}) == len(docs)


def test_ingest_into_chroma_is_idempotent(tmp_path):
    settings = dataclasses.replace(get_settings(), chroma_dir=tmp_path / "chroma")
    embeddings = DeterministicFakeEmbedding(size=64)

    first = ingest(settings, embeddings)
    again = ingest(settings, embeddings, reset=False)

    assert first.stored == first.chunks
    assert again.stored == first.stored

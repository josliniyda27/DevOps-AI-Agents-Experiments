"""
Checks on the real knowledge base, so a bad entry or a stale index fails the test run.
To fix a failure: edit the entry, then run `python -m src.knowledge_base.workflow`.
"""

import collections

import pytest

from src.config import get_settings
from src.knowledge_base import KnowledgeBaseLoader
from src.knowledge_base.workflow import sync_indexes, validate

# Two entries exist twice (fundamentals.json and their own files); the copy in fundamentals.json is used.
# Do not add to this list: give a new entry a new id.
KNOWN_DUPLICATE_IDS = {"llm-001", "rag-001"}


@pytest.fixture(scope="module")
def data_dir():
    return get_settings().data_dir


@pytest.fixture(scope="module")
def loaded(data_dir):
    return KnowledgeBaseLoader(data_dir).load_entries()


def test_the_knowledge_base_passes_validation(data_dir):
    report = validate(data_dir)
    assert report.errors == [], [f"{i.where}: {i.message}" for i in report.errors[:5]]


def test_there_are_no_warnings_beyond_the_two_known_duplicates(data_dir):
    report = validate(data_dir)
    unexpected = [i for i in report.warnings if not (i.message.startswith("duplicate id") and i.where in KNOWN_DUPLICATE_IDS)]
    assert unexpected == [], [f"{i.where}: {i.message}" for i in unexpected[:5]]


def test_the_index_files_match_the_entries(data_dir):
    assert sync_indexes(data_dir, write=False) == [], "run: python -m src.knowledge_base.workflow"


def test_ids_and_questions_are_unique(loaded):
    assert set(loaded.duplicates) <= KNOWN_DUPLICATE_IDS
    questions = collections.Counter(e["question"].strip().lower() for e in loaded.entries)
    assert [q for q, n in questions.items() if n > 1] == []


def test_every_entry_cites_an_official_source(loaded):
    for entry in loaded.entries:
        links = [e["url"] for e in entry.get("official_evidence", [])] + list(entry.get("official_links", []))
        assert links and all(url.startswith("https://") for url in links), entry["id"]


def test_entries_written_by_the_agents_record_where_they_came_from(loaded):
    written = [e for e in loaded.entries if "provenance" in e]
    assert written, "expected agent-written entries"
    for entry in written:
        provenance = entry["provenance"]
        assert provenance["method"] == "agentic-workflow" and provenance["grounded"] is True, entry["id"]
        assert provenance["source_url"].startswith("https://") and provenance["run"], entry["id"]
        assert entry["official_evidence"][0]["url"] == provenance["source_url"], entry["id"]


def test_the_knowledge_base_covers_each_domain_in_depth(loaded):
    folders = collections.Counter(e["source"].split("/")[0] for e in loaded.entries)
    assert folders["Cloud"] >= 50 and folders["DevOps"] >= 30 and folders["Workflows"] >= 8

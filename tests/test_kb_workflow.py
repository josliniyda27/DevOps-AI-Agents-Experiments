import dataclasses
import json

import httpx
import pytest

from src.config import get_settings
from src.knowledge_base import workflow
from src.knowledge_base.workflow import (
    check_links, collect_links, self_check, sync_indexes, validate,
)
from tests.kb_helpers import entry, write_kb


def _messages(report, level):
    return [(i.where, i.message) for i in report.issues if i.level == level]


# ---------- validate ----------

def test_a_clean_knowledge_base_has_no_issues(tmp_path):
    report = validate(write_kb(tmp_path, {"Cloud/AWS/x.json": entry()}))
    assert report.entries == 1 and report.issues == [] and report.per_category == {"AWS Cloud": 1}


def test_broken_json_is_reported_by_file_and_stops_early(tmp_path):
    report = validate(write_kb(tmp_path, {"Cloud/AWS/good.json": entry(), "Cloud/AWS/bad.json": "{ not json"}))
    assert [w for w, _ in _messages(report, "error")] == ["Cloud/AWS/bad.json"] and "invalid JSON" in report.errors[0].message


@pytest.mark.parametrize("change, expected", [
    ({"id": "AWS_X"}, "id must look like"),
    ({"answer": "Too short."}, "shorter than"),
    ({"official_evidence": [{"title": "t", "url": "http://insecure.example.com", "source_type": "x"}]}, "must start with https://"),
])
def test_quality_errors_block_the_workflow(tmp_path, change, expected):
    report = validate(write_kb(tmp_path, {"Cloud/AWS/x.json": entry(**change)}))
    assert any(expected in m for _, m in _messages(report, "error"))


def test_missing_required_fields_are_schema_errors(tmp_path):
    broken = entry()
    del broken["answer"]
    report = validate(write_kb(tmp_path, {"Cloud/AWS/x.json": broken}))
    assert any(m.startswith("schema:") for _, m in _messages(report, "error"))


def test_softer_problems_are_warnings_only(tmp_path):
    thin = entry(question="What is it", key_concepts=["One"], workflow=["Only step"], official_evidence=[])
    report = validate(write_kb(tmp_path, {"Cloud/AWS/x.json": thin}))
    warnings = " | ".join(m for _, m in _messages(report, "warning"))
    assert report.errors == [] and all(t in warnings for t in ("does not end with '?'", "key_concepts", "workflow steps", "official_evidence"))


def test_duplicate_ids_and_topics_are_warnings(tmp_path):
    report = validate(write_kb(tmp_path, {
        "Cloud/AWS/a.json": entry("aws-a-001", "Same Topic"), "Cloud/AWS/b.json": entry("aws-a-001", "Other"),
        "Cloud/AWS/c.json": entry("aws-c-001", "same topic"),
    }))
    text = " | ".join(m for _, m in _messages(report, "warning"))
    assert "duplicate id" in text and "same topic" in text and report.errors == []


# ---------- indexes ----------

def _pointers(kb, file):
    return json.loads((kb / "indexes" / file).read_text())


def test_indexes_are_built_from_the_entries_by_domain(tmp_path):
    kb = write_kb(tmp_path, {
        "Cloud/AWS/s3.json": entry("aws-s3-001", "S3"), "DevOps/docker.json": entry("docker-001", "Docker", "DevOps"),
        "Workflows/aws_site.json": entry("wf-aws-site-001", "Static Site", "AWS Workflows"),
    })
    changed = sync_indexes(kb)

    assert {"aws_index.json", "devops_index.json", "workflows_index.json", "knowledge_index.json"} <= set(changed)
    assert _pointers(kb, "aws_index.json")["aws_services"] == [{"id": "aws-s3-001", "file": "s3.json", "topic": "S3", "category": "AWS Cloud"}]
    assert list(_pointers(kb, "knowledge_index.json")["knowledge_domains"]) == ["AWS_Cloud", "DevOps", "Workflows"]


def test_syncing_twice_changes_nothing_the_second_time(tmp_path):
    kb = write_kb(tmp_path, {"Cloud/AWS/s3.json": entry("aws-s3-001", "S3")})
    sync_indexes(kb)
    assert sync_indexes(kb) == []


def test_existing_pointer_categories_survive_and_new_entries_use_their_group(tmp_path):
    kb = write_kb(tmp_path, {
        "Cloud/AWS/s3.json": entry("aws-s3-001", "S3"),
        "Cloud/AWS/kms.json": entry("aws-kms-001", "KMS", group="Security"),
        "indexes/aws_index.json": {"aws_services": [{"id": "aws-s3-001", "file": "s3.json", "topic": "S3", "category": "Storage"}]},
    })
    sync_indexes(kb)
    assert [(p["id"], p["category"]) for p in _pointers(kb, "aws_index.json")["aws_services"]] == [("aws-s3-001", "Storage"), ("aws-kms-001", "Security")]


def test_pointers_to_deleted_entries_are_pruned(tmp_path):
    kb = write_kb(tmp_path, {
        "Cloud/AWS/s3.json": entry("aws-s3-001", "S3"),
        "indexes/aws_index.json": {"aws_services": [{"id": "aws-gone-001", "file": "gone.json", "topic": "Gone", "category": "X"},
                                                   {"id": "aws-s3-001", "file": "s3.json", "topic": "S3", "category": "Storage"}]},
    })
    sync_indexes(kb)
    assert [p["id"] for p in _pointers(kb, "aws_index.json")["aws_services"]] == ["aws-s3-001"]


def test_check_mode_reports_drift_without_writing(tmp_path):
    kb = write_kb(tmp_path, {"Cloud/AWS/s3.json": entry("aws-s3-001", "S3")})
    assert "aws_index.json" in sync_indexes(kb, write=False)
    assert not (kb / "indexes").exists()


# ---------- the command ----------

def _run(monkeypatch, kb, *args):
    settings = dataclasses.replace(get_settings(), data_dir=kb)
    monkeypatch.setattr(workflow, "get_settings", lambda: settings)
    return workflow.main(list(args))


def test_check_mode_exit_codes(tmp_path, monkeypatch, capsys):
    kb = write_kb(tmp_path, {"Cloud/AWS/s3.json": entry("aws-s3-001", "S3")})
    assert _run(monkeypatch, kb, "--check") == 1                       # indexes missing
    sync_indexes(kb)
    assert _run(monkeypatch, kb, "--check") == 0                       # in sync
    write_kb(tmp_path, {"Cloud/AWS/bad.json": "{"})
    assert _run(monkeypatch, kb, "--check") == 1                       # broken file
    assert "invalid JSON" in capsys.readouterr().out


def test_strict_mode_fails_on_warnings(tmp_path, monkeypatch):
    kb = write_kb(tmp_path, {"Cloud/AWS/s3.json": entry("aws-s3-001", "S3", question="What is it")})
    sync_indexes(kb)
    assert _run(monkeypatch, kb, "--check") == 0 and _run(monkeypatch, kb, "--check", "--strict") == 1


# ---------- self-check ----------

def test_self_check_lists_entries_their_own_question_does_not_find():
    entries = [entry("a-001", "A"), entry("b-001", "B"), entry("c-001", "C")]
    rankings = {"What is A?": ["a-001", "x"], "What is B?": ["x", "y", "z", "b-001"], "What is C?": ["x"]}
    result = self_check(entries, lambda q: rankings[q], top=3)

    assert (result.total, result.passed) == (3, 1)
    assert result.failures == [("b-001", "4", "x"), ("c-001", None, "x")]


# ---------- links ----------

def test_links_are_collected_with_the_entries_that_cite_them():
    a = entry("a-001", official_evidence=[{"title": "t", "url": "https://x.example/1", "source_type": "s"}], official_links=["https://x.example/2"])
    b = entry("b-001", official_evidence=[{"title": "t", "url": "https://x.example/1", "source_type": "s"}])
    assert collect_links([a, b]) == {"https://x.example/1": ["a-001", "b-001"], "https://x.example/2": ["a-001"]}


def test_link_check_reports_only_the_unhealthy_ones():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "boom.example":
            raise httpx.ConnectError("no route")
        if host == "nohead.example":                   # some servers refuse HEAD but serve GET
            return httpx.Response(405 if request.method == "HEAD" else 200)
        return httpx.Response({"ok.example": 200, "gone.example": 404, "bot.example": 403}[host])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    problems = check_links([f"https://{h}/p" for h in ("ok.example", "nohead.example", "gone.example", "bot.example", "boom.example")], client=client)

    assert problems == {
        "https://gone.example/p": "HTTP 404",
        "https://bot.example/p": "blocked (403); check manually",
        "https://boom.example/p": "unreachable (ConnectError)",
    }

"""Turn an approved draft into an entry, reject duplicates, stage it, and later merge staged entries."""

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from kb_agents.domains import WORKFLOWS_FOLDER, Domain
from kb_agents.models import Draft, Proposal
from src.knowledge_base import KnowledgeBaseLoader
from src.knowledge_base.validator import KnowledgeBaseValidator
from src.knowledge_base.workflow import entry_issues

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_ANSWER_CHARS = 450
DUPLICATE_SIMILARITY = 0.88
COURSE = "AI-Assisted DevOps"


@dataclass
class ExistingKB:
    ids: set[str] = field(default_factory=set)
    topics: set[str] = field(default_factory=set)        # lower-cased
    topic_names: list[str] = field(default_factory=list)


def existing_state(data_dir: Path) -> ExistingKB:
    entries = KnowledgeBaseLoader(data_dir).load_entries().entries
    return ExistingKB({e["id"] for e in entries}, {e["topic"].strip().lower() for e in entries}, sorted({e["topic"] for e in entries}))


def slug_of(domain: Domain, proposal: Proposal) -> str:
    """The planner's slug without a redundant vendor prefix ('aws-cloudfront' -> 'cloudfront'), so ids read 'aws-cloudfront-001'."""
    slug = proposal.slug.strip()
    changed = True
    while changed:
        changed = False
        for prefix in (f"{domain.key}-", "amazon-", "aws-"):
            if slug.startswith(prefix) and len(slug) > len(prefix):
                slug, changed = slug[len(prefix):], True
    return slug


def relative_path(domain: Domain, proposal: Proposal) -> str:
    name = slug_of(domain, proposal).replace("-", "_")
    return f"{WORKFLOWS_FOLDER}/{domain.key}_{name}.json" if proposal.kind == "workflow" else f"{domain.concept_folder}/{name}.json"


def build_entry(domain: Domain, proposal: Proposal, draft: Draft, *, grounded: bool, model: str, run_id: str) -> dict:
    workflow = proposal.kind == "workflow"
    slug = slug_of(domain, proposal)
    clean = lambda items, limit: [i.strip() for i in items if i and i.strip()][:limit]     # noqa: E731

    topic = proposal.topic.strip()
    fallback = "Step-by-step workflow" if workflow else proposal.category      # when the model only repeats the topic name
    subtopic = next((c.strip() for c in (draft.subtopic, proposal.subtopic, fallback) if c.strip() and c.strip().lower() != topic.lower()), "")

    entry = {
        "id": f"wf-{domain.key}-{slug}-001" if workflow else f"{domain.id_prefix}{slug}-001",
        "course": COURSE,
        "category": domain.workflow_category if workflow else (proposal.category if proposal.category in domain.categories else domain.categories[0]),
        "topic": topic,
        "subtopic": subtopic,
        "question": proposal.question.strip(),
        "answer": draft.answer.strip(),
        "course_context": {
            "module": "Workflows" if workflow else (proposal.module if proposal.module in domain.modules else domain.modules[0]),
            "usage": draft.usage.strip(),
        },
        "key_concepts": clean(draft.key_concepts, 8),
        "workflow": clean(draft.workflow, 10),
        "devops_application": draft.devops_application.strip(),
        "official_evidence": [{
            "title": "Official documentation" if workflow else f"{topic} Documentation",
            "url": proposal.source_url.strip(),
            "source_type": "official_documentation",
        }],
        "related_topics": clean(draft.related_topics, 6),
    }
    if proposal.group and proposal.group in domain.groups and not workflow:
        entry["group"] = proposal.group
    entry["provenance"] = {"method": "agentic-workflow", "model": model, "grounded": grounded,
                           "source_url": proposal.source_url.strip(), "run": run_id}
    return entry


# An entry must describe its topic, not its source. These phrases mean the draft is about the page it was given.
META_PHRASES = ("not mentioned", "not specified", "no information", "provided source", "source documentation",
                "the source does", "the source doesn", "the source states", "according to the source",
                "the documentation does not", "not described in")


def talks_about_its_source(entry: dict) -> str | None:
    text = " ".join([entry["answer"], entry["devops_application"], entry["course_context"]["usage"], *entry["workflow"]]).lower()
    return next((p for p in META_PHRASES if p in text), None)


def entry_problems(entry: dict, slug: str) -> list[str]:
    """Deterministic gate: schema, the workflow's quality rules, and the agents' own limits."""
    problems = []
    if not entry["subtopic"]:
        problems.append("subtopic is empty or repeats the topic name")
    if not SLUG.match(slug):
        problems.append(f"slug {slug!r} is not lower-case words joined by hyphens")
    schema_error = KnowledgeBaseValidator().error_for(entry)
    if schema_error:
        problems.append(f"schema: {schema_error}")
        return problems
    problems += [i.message for i in entry_issues(entry) if i.level == "error"]
    meta = talks_about_its_source(entry)
    if meta:
        problems.append(f"the entry talks about its source instead of the topic (\"{meta}\")")
    if len(entry["answer"]) > MAX_ANSWER_CHARS:
        problems.append(f"answer longer than {MAX_ANSWER_CHARS} characters")
    if len(entry["key_concepts"]) < 3:
        problems.append("fewer than 3 key concepts")
    if len(entry["workflow"]) < 3:
        problems.append("fewer than 3 workflow steps")
    return problems


def check_duplicate(entry: dict, existing: ExistingKB, batch_topics: set[str],
                    nearest: Callable[[str], tuple[float, str] | None] | None = None) -> str | None:
    """Why this entry duplicates knowledge we already have (or are about to add), or None."""
    topic = entry["topic"].strip().lower()
    if entry["id"] in existing.ids:
        return f"id {entry['id']} already exists"
    if topic in existing.topics:
        return "topic is already in the knowledge base"
    if topic in batch_topics:
        return "same topic as another entry in this run"
    if nearest:
        match = nearest(entry["question"])
        if match and match[0] >= DUPLICATE_SIMILARITY:
            return f"near-duplicate of {match[1]} (similarity {match[0]:.2f})"
    return None


def dump_entry(entry: dict) -> str:
    """JSON in the house style: short lists on one line, steps one per line."""
    inline = {"key_concepts", "related_topics"}
    lines = []
    for n, (key, value) in enumerate(entry.items()):
        if key in inline:
            body = json.dumps(value, ensure_ascii=False)
        else:
            body = json.dumps(value, indent=2, ensure_ascii=False).replace("\n", "\n  ")
        lines.append(f"  {json.dumps(key)}: {body}" + ("," if n < len(entry) - 1 else ""))
    return "{\n" + "\n".join(lines) + "\n}\n"


def write_stage(stage_dir: Path, accepted: list[tuple[str, dict]], report: dict) -> None:
    for rel, entry in accepted:
        path = stage_dir / "entries" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_entry(entry), encoding="utf-8")
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class MergeResult:
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)    # destination already exists; never overwritten


def merge_stage(stage_dir: Path, data_dir: Path) -> MergeResult:
    result = MergeResult()
    for source in sorted((stage_dir / "entries").rglob("*.json")):
        rel = source.relative_to(stage_dir / "entries")
        target = data_dir / rel
        if target.exists():
            result.skipped.append(rel.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        result.copied.append(rel.as_posix())
    (stage_dir / "merged.json").write_text(json.dumps({"copied": result.copied, "skipped": result.skipped}, indent=2) + "\n", encoding="utf-8")
    return result

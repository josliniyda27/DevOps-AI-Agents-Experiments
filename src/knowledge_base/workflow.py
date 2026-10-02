"""
Knowledge-base workflow: validate -> sync indexes -> load into Chroma (+ optional self-check and link check).

    python -m src.knowledge_base.workflow                 # validate, sync indexes, rebuild the vector store
    python -m src.knowledge_base.workflow --check         # CI mode: validate and verify indexes; write nothing
    python -m src.knowledge_base.workflow --self-check    # does each entry's own question retrieve it?
    python -m src.knowledge_base.workflow --check-links   # do the documentation links respond? (needs network)

To add knowledge: copy docs/entry_template.json into the right folder, fill it in, run this workflow.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.config import get_settings
from src.knowledge_base.loader import INDEX_DIR, KnowledgeBaseLoader

ID_FORMAT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d{3}$")
MIN_ANSWER_CHARS = 40

# folder under the data directory -> (index file, key inside it, domain name in knowledge_index.json)
DOMAINS: dict[str, tuple[str, str, str]] = {
    "Cloud/AWS": ("aws_index.json", "aws_services", "AWS_Cloud"),
    "DevOps": ("devops_index.json", "devops_topics", "DevOps"),
    "genai_fundamentals": ("genai_index.json", "genai_fundamentals", "GenAI_Fundamentals"),
    "Course_projects": ("course_projects_index.json", "course_projects", "Course_Projects"),
    "Workflows": ("workflows_index.json", "workflows", "Workflows"),
}
MASTER_INDEX = "knowledge_index.json"


@dataclass(frozen=True)
class Issue:
    level: str        # "error" | "warning"
    where: str        # file path or entry id
    message: str


@dataclass
class QualityReport:
    entries: int = 0
    issues: list[Issue] = field(default_factory=list)
    per_category: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


# ---------------------------------------------------------------- 1. validate

def _entry_files(data_dir: Path) -> list[Path]:
    return [p for p in sorted(data_dir.rglob("*.json")) if INDEX_DIR not in p.relative_to(data_dir).parts]


def entry_issues(entry: dict) -> list[Issue]:
    """Quality rules for one (already schema-valid) entry."""
    where, issues = entry["id"], []

    if not ID_FORMAT.match(entry["id"]):
        issues.append(Issue("error", where, "id must look like 'aws-s3-001' (lower-case words, then a 3-digit number)"))
    if len(entry["answer"].strip()) < MIN_ANSWER_CHARS:
        issues.append(Issue("error", where, f"answer is shorter than {MIN_ANSWER_CHARS} characters"))
    if not entry["question"].strip().endswith("?"):
        issues.append(Issue("warning", where, "question does not end with '?'"))
    if len(entry.get("key_concepts") or []) < 3:
        issues.append(Issue("warning", where, "fewer than 3 key_concepts"))
    if len(entry.get("workflow") or []) < 3 and "use_cases" not in entry:
        issues.append(Issue("warning", where, "fewer than 3 workflow steps"))

    urls = [e.get("url", "") for e in entry.get("official_evidence", []) if isinstance(e, dict)] + list(entry.get("official_links", []))
    if not urls:
        issues.append(Issue("warning", where, "no official_evidence link"))
    for url in urls:
        if not url.startswith("https://"):
            issues.append(Issue("error", where, f"link must start with https://: {url!r}"))
    if len(set(urls)) != len(urls):
        issues.append(Issue("warning", where, "the same link is listed twice"))
    return issues


def validate(data_dir: Path) -> QualityReport:
    """Schema plus quality rules. Errors block the workflow; warnings are advice."""
    report = QualityReport()

    for path in _entry_files(data_dir):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            report.issues.append(Issue("error", path.relative_to(data_dir).as_posix(), f"invalid JSON: {error}"))
    if report.errors:
        return report      # the loader cannot read broken files; fix the syntax first

    loaded = KnowledgeBaseLoader(data_dir).load_entries()
    report.entries = len(loaded.entries)
    report.per_category = dict(sorted(Counter(e["category"] for e in loaded.entries).items()))

    for source, message in loaded.invalid:
        report.issues.append(Issue("error", source, f"schema: {message}"))
    for entry_id in loaded.duplicates:
        report.issues.append(Issue("warning", entry_id, "duplicate id in another file; only the first is used"))

    topics: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entry in loaded.entries:
        topics[(entry["category"], entry["topic"].strip().lower())].append(entry["id"])
        report.issues.extend(entry_issues(entry))

    for (category, topic), ids in topics.items():
        if len(ids) > 1:
            report.issues.append(Issue("warning", ", ".join(ids), f"same topic '{topic}' appears more than once in '{category}'"))

    return report


# ---------------------------------------------------------------- 2. indexes

def _dump_index(pointers_by_key: dict) -> str:
    """Same layout as the hand-written indexes: one compact pointer per line."""
    def pointer(p: dict) -> str:
        return "{ " + ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in p.items()) + " }"

    lines = ["{"]
    keys = list(pointers_by_key)
    for n, key in enumerate(keys):
        value = pointers_by_key[key]
        if isinstance(value, dict):                           # the master index: {domain: [pointers]}
            lines.append(f'  {json.dumps(key)}: {{')
            domains = list(value)
            for m, domain in enumerate(domains):
                body = ",\n".join(f"      {pointer(p)}" for p in value[domain])
                lines.append(f'    {json.dumps(domain)}: [\n{body}\n    ]' + ("," if m < len(domains) - 1 else ""))
            lines.append("  }" + ("," if n < len(keys) - 1 else ""))
        else:
            body = ",\n".join(f"    {pointer(p)}" for p in value)
            lines.append(f'  {json.dumps(key)}: [\n{body}\n  ]' + ("," if n < len(keys) - 1 else ""))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _old_categories(index_dir: Path, file: str) -> dict[str, str]:
    path = index_dir / file
    if not path.exists():
        return {}
    found: dict[str, str] = {}
    for value in json.loads(path.read_text(encoding="utf-8")).values():
        pointers = [p for group in value.values() for p in group] if isinstance(value, dict) else value
        found.update({p["id"]: p["category"] for p in pointers if isinstance(p, dict) and "id" in p})
    return found


def sync_indexes(data_dir: Path, write: bool = True) -> list[str]:
    """
    Rebuild the index files from the entry files (the entries are the source of truth).
    Keeps the category an existing pointer already had; new pointers use the entry's `group`, else its category.
    Returns the index files that changed (or, with write=False, that would change).
    """
    index_dir = data_dir / INDEX_DIR
    entries = KnowledgeBaseLoader(data_dir).load_entries().entries
    changed: list[str] = []
    master: dict[str, list[dict]] = {}

    for folder, (file, key, domain) in DOMAINS.items():
        old = _old_categories(index_dir, file)
        old_order = list(old)
        members = [e for e in entries if e["source"].startswith(folder + "/")]
        members.sort(key=lambda e: (old_order.index(e["id"]) if e["id"] in old_order else len(old_order), e["source"], e["id"]))

        pointers = [{
            "id": e["id"],
            "file": Path(e["source"]).name,
            "topic": e["topic"],
            "category": old.get(e["id"]) or e.get("group") or e["category"],
        } for e in members]
        master[domain] = pointers

        if not pointers and not (index_dir / file).exists():
            continue
        text = _dump_index({key: pointers})
        if not (index_dir / file).exists() or (index_dir / file).read_text(encoding="utf-8") != text:
            changed.append(file)
            if write:
                index_dir.mkdir(exist_ok=True)
                (index_dir / file).write_text(text, encoding="utf-8")

    text = _dump_index({"knowledge_domains": {d: p for d, p in master.items() if p}})
    master_path = index_dir / MASTER_INDEX
    if not master_path.exists() or master_path.read_text(encoding="utf-8") != text:
        changed.append(MASTER_INDEX)
        if write:
            master_path.write_text(text, encoding="utf-8")
    return changed


# ---------------------------------------------------------------- 3. self-check

@dataclass
class SelfCheck:
    total: int
    failures: list[tuple[str, str | None, str]]   # (entry id, rank or None, best other hit)

    @property
    def passed(self) -> int:
        return self.total - len(self.failures)


def self_check(entries: Sequence[dict], ranked_ids: Callable[[str], list[str]], top: int = 3) -> SelfCheck:
    """
    Does each entry's own question retrieve it? `ranked_ids(question)` returns entry ids, best first.
    An entry that is not found in the top results has a weak question or overlaps another entry.
    """
    failures = []
    for entry in entries:
        ranking = ranked_ids(entry["question"])
        if entry["id"] not in ranking[:top]:
            rank = str(ranking.index(entry["id"]) + 1) if entry["id"] in ranking else None
            failures.append((entry["id"], rank, ranking[0] if ranking else "nothing"))
    return SelfCheck(len(entries), failures)


# ---------------------------------------------------------------- 4. links

def collect_links(entries: Sequence[dict]) -> dict[str, list[str]]:
    """{url: [ids of the entries that cite it]}"""
    links: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        urls = [e["url"] for e in entry.get("official_evidence", []) if isinstance(e, dict) and e.get("url")]
        for url in urls + list(entry.get("official_links", [])):
            if entry["id"] not in links[url]:
                links[url].append(entry["id"])
    return dict(links)


def check_links(links: Sequence[str], client=None, workers: int = 8) -> dict[str, str]:
    """
    Probe each link. Returns {url: problem} for the ones that do not look healthy.
    403/429 are reported as 'blocked', since many sites refuse automated requests.
    """
    import httpx

    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=10, headers={"User-Agent": "kb-link-check/1.0"})

    def probe(url: str) -> tuple[str, str | None]:
        try:
            status = client.head(url).status_code
            if status >= 400:
                status = client.get(url).status_code
        except httpx.HTTPError as error:
            return url, f"unreachable ({type(error).__name__})"
        if status in (403, 429):
            return url, f"blocked ({status}); check manually"
        return url, None if status < 400 else f"HTTP {status}"

    try:
        with ThreadPoolExecutor(workers) as pool:
            return {url: problem for url, problem in pool.map(probe, links) if problem}
    finally:
        if own_client:
            client.close()


# ---------------------------------------------------------------- CLI

def _print_issues(issues: Sequence[Issue], limit: int = 40) -> None:
    for issue in list(issues)[:limit]:
        print(f"  {issue.level.upper():7} {issue.where}: {issue.message}")
    if len(issues) > limit:
        print(f"  ... and {len(issues) - limit} more")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the knowledge base, sync its indexes and load it into Chroma.")
    parser.add_argument("--check", action="store_true", help="CI mode: validate and verify the indexes are in sync; write nothing")
    parser.add_argument("--no-ingest", action="store_true", help="skip rebuilding the vector store")
    parser.add_argument("--self-check", action="store_true", help="check each entry's own question retrieves it (needs the vector store)")
    parser.add_argument("--check-links", action="store_true", help="probe every documentation link (needs network)")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args(argv)

    settings = get_settings()
    data_dir = settings.data_dir

    print("1. Validate")
    report = validate(data_dir)
    print(f"   {report.entries} entries | {len(report.errors)} errors | {len(report.warnings)} warnings")
    for category, count in report.per_category.items():
        print(f"     {category:<26}{count}")
    _print_issues(report.issues)
    if report.errors or (args.strict and report.warnings):
        print("\nFix the problems above and run again.")
        return 1

    print("\n2. Indexes")
    drift = sync_indexes(data_dir, write=not args.check)
    if args.check:
        print("   out of date: " + ", ".join(drift) if drift else "   in sync")
        if drift:
            print("\nRun `python -m src.knowledge_base.workflow` to update them.")
            return 1
    else:
        print("   updated: " + ", ".join(drift) if drift else "   already in sync")

    exit_code = 0
    if not args.check and not args.no_ingest:
        from src.retrieval.ingest import ingest

        print("\n3. Load into Chroma")
        summary = ingest(settings)
        print(f"   {summary.entries} entries -> {summary.chunks} chunks stored ({summary.embedding_model})")

    if args.self_check:
        from src.retrieval.rerank import NoReranker
        from src.retrieval.retriever import load_store, retrieve

        print("\n4. Self-check: does each entry's question retrieve it?")
        store = load_store(settings)
        entries = KnowledgeBaseLoader(data_dir).load_entries().entries
        result = self_check(entries, lambda q: [h.entry["id"] for h in retrieve(
            q, k=10, min_score=-1, settings=None, store=store, reranker=NoReranker()).hits])
        print(f"   {result.passed}/{result.total} found in the top 3")
        for entry_id, rank, other in result.failures[:25]:
            print(f"   MISS {entry_id}: rank {rank or '>10'}, top hit was {other}")

    if args.check_links:
        print("\n5. Links")
        entries = KnowledgeBaseLoader(data_dir).load_entries().entries
        links = collect_links(entries)
        problems = check_links(list(links))
        print(f"   {len(links) - len(problems)}/{len(links)} links responded")
        for url, problem in sorted(problems.items()):
            print(f"   {problem:<32}{url}   (cited by {', '.join(links[url][:3])})")
        exit_code = 1 if args.strict and problems else exit_code

    print("\nDone.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

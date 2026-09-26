"""Small builders shared by the knowledge-base tests."""

import json
from pathlib import Path


def entry(entry_id="aws-x-001", topic="Example Service", category="AWS Cloud", **over) -> dict:
    base = {
        "id": entry_id, "course": "AI-Assisted DevOps", "category": category, "topic": topic,
        "subtopic": "A thing", "question": f"What is {topic}?",
        "answer": f"{topic} is a service that does something useful and well defined for engineers.",
        "course_context": {"module": "AWS Basics", "usage": "Used in projects."},
        "key_concepts": ["One", "Two", "Three"], "workflow": ["Step one", "Step two", "Step three"],
        "devops_application": "Used by DevOps teams.",
        "official_evidence": [{"title": "Docs", "url": "https://docs.example.com/x", "source_type": "official_documentation"}],
        "related_topics": ["A", "B", "C"],
    }
    return base | over


def write_kb(root: Path, files: dict[str, dict | list | str]) -> Path:
    """Write {relative path: json data (or raw text)} under root/kb and return that directory."""
    kb = root / "kb"
    for rel, data in files.items():
        path = kb / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return kb

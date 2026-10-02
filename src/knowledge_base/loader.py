import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .validator import KnowledgeBaseValidator

INDEX_DIR = "indexes"
DEFAULT_COURSE = "AI-Assisted DevOps"


@dataclass
class LoadReport:
    """Result of loading the knowledge base."""
    entries: list[dict] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)          # ids skipped as duplicates
    invalid: list[tuple[str, str]] = field(default_factory=list)  # (source file, error)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class KnowledgeBaseLoader:
    """
    Loads knowledge base entries from the JSON files under `data_dir`.

    Every non-index `*.json` file is read (a file may hold one entry or a list of
    entries), normalised to the standard schema, validated and de-duplicated.
    The index files are used only to look up ids for files that lack one.
    """

    def __init__(self, data_dir: str | Path = "data/knowledge_base_v1"):
        self.data_dir = Path(data_dir)
        self.validator = KnowledgeBaseValidator()

    def load_file(self, filename: str):
        """Load a single JSON file (path relative to data_dir)."""
        filepath = self.data_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Knowledge base file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_index(self, index_file: str) -> list:
        """Load an index file and return its flattened pointer entries."""
        data = self.load_file(f"{INDEX_DIR}/{index_file}")
        if isinstance(data, dict):
            pointers = []
            for value in data.values():
                pointers.extend(value if isinstance(value, list) else [value])
            return pointers
        return data if isinstance(data, list) else []

    def _index_lookup(self) -> dict[str, dict]:
        """Map entry filename -> index pointer ({id, file, topic, category})."""
        lookup = {}
        for path in sorted((self.data_dir / INDEX_DIR).glob("*.json")):
            for pointer in self.load_index(path.name):
                if isinstance(pointer, dict) and "file" in pointer:
                    lookup[pointer["file"]] = pointer
        return lookup

    def _normalise(self, raw: dict, path: Path, lookup: dict[str, dict]) -> dict:
        """Fill in fields that some files (e.g. course projects) don't carry."""
        entry = dict(raw)
        pointer = lookup.get(path.name, {})
        folder = path.parent.name
        topic = entry.get("topic") or pointer.get("topic") or path.stem.replace("_", " ").title()

        entry.setdefault("topic", topic)
        entry.setdefault("id", pointer.get("id") or f"{_slug(folder)}-{_slug(path.stem)}-001")
        entry.setdefault("course", DEFAULT_COURSE)
        entry.setdefault("category", folder.replace("_", " ").title())
        entry.setdefault("question", f"What is {topic}?")
        if "answer" not in entry and entry.get("description"):
            entry["answer"] = entry["description"]
        return entry

    def load_entries(self) -> LoadReport:
        """Load, normalise, validate and de-duplicate every entry file."""
        report = LoadReport()
        lookup = self._index_lookup()
        seen: set[str] = set()

        for path in sorted(self.data_dir.rglob("*.json")):
            if INDEX_DIR in path.relative_to(self.data_dir).parts:
                continue
            source = path.relative_to(self.data_dir).as_posix()
            with open(path, "r", encoding="utf-8") as f:
                content = json.load(f)

            for raw in content if isinstance(content, list) else [content]:
                if not isinstance(raw, dict):
                    report.invalid.append((source, "entry is not a JSON object"))
                    continue
                entry = self._normalise(raw, path, lookup)
                entry["source"] = source

                error = self.validator.error_for(entry)
                if error:
                    report.invalid.append((source, error))
                elif entry["id"] in seen:
                    report.duplicates.append(entry["id"])
                else:
                    seen.add(entry["id"])
                    report.entries.append(entry)

        return report

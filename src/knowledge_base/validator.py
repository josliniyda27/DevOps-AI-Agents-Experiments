import jsonschema


class KnowledgeBaseValidator:
    """
    Validates knowledge base entries against a schema.
    """

    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "course": {"type": "string"},
            "category": {"type": "string"},
            "topic": {"type": "string"},
            "subtopic": {"type": "string"},
            "question": {"type": "string"},
            "answer": {"type": "string"},
            "course_context": {"type": "object"},
            "key_concepts": {"type": "array"},
            "workflow": {"type": "array"},
            "devops_application": {"type": "string"},
            "official_evidence": {"type": "array"},
            "related_topics": {"type": "array"}
        },
        "required": ["id", "course", "category", "topic", "question", "answer"]
    }

    def error_for(self, entry: dict) -> str | None:
        """Return a validation error message, or None if the entry is valid."""
        try:
            jsonschema.validate(instance=entry, schema=self.schema)
            return None
        except jsonschema.ValidationError as e:
            return e.message

    def validate_entry(self, entry: dict) -> bool:
        """Validate a single knowledge base entry."""
        error = self.error_for(entry)
        if error:
            print(f"Validation error in entry {entry.get('id', 'unknown')}: {error}")
        return error is None

    def validate_entries(self, entries: list[dict]) -> list[tuple[str, str]]:
        """Validate many entries; return (entry id, error) for each invalid one."""
        errors = []
        for entry in entries:
            error = self.error_for(entry)
            if error:
                errors.append((entry.get("id", "unknown"), error))
        return errors

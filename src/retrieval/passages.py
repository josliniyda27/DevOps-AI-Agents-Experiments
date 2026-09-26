"""
Render a knowledge-base entry as a passage for the re-ranker and the LLM.

Unlike the text that is embedded (see chunker.py), a passage reads as plain notes: the JSON field
names ("key_concepts", "workflow", ...) are deliberately not used as labels. When they were, the model
recited them back ("Key concepts include... The workflow involves...").
"""


def _list(items: list) -> str:
    return "; ".join(str(i) for i in items)


def entry_to_passage(entry: dict) -> str:
    subtopic = f" - {entry['subtopic']}" if entry.get("subtopic") else ""
    lines = [f"{entry['topic']}{subtopic} ({entry['category']})", entry["answer"]]

    if entry.get("key_concepts"):
        lines.append(f"Core ideas: {_list(entry['key_concepts'])}.")
    if entry.get("workflow"):
        lines.append(f"Typical sequence: {' → '.join(str(step) for step in entry['workflow'])}.")
    if entry.get("devops_application"):
        lines.append(f"In practice: {entry['devops_application']}")
    if entry.get("use_cases"):
        lines.append(f"Example uses: {_list(entry['use_cases'])}.")

    return "\n".join(lines)

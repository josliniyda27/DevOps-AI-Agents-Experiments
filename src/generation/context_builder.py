from html import escape
from typing import List

from langchain_core.documents import Document


def _clean(text: str) -> str:
    """Trim each line and drop blank ones, but keep the line structure (it carries meaning)."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line).replace("<", "&lt;").replace(">", "&gt;")


def format_docs_to_xml(docs: List[Document]) -> str:
    """
    Context Engineering step:
    - Drops duplicate documents (same id or same text)
    - Labels each document with its id, topic and category
    - Escapes angle brackets so document text cannot forge tags such as </context>
    """
    if not docs:
        return "<empty_context>No matching documents found.</empty_context>"

    formatted_blocks = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()

    for idx, doc in enumerate(docs, start=1):
        text = _clean(doc.page_content)
        doc_id = str(doc.metadata.get("id", f"doc_{idx}"))

        if doc_id in seen_ids or text in seen_texts:
            continue
        seen_ids.add(doc_id)
        seen_texts.add(text)

        attributes = f'id="{escape(doc_id)}"'
        for name in ("topic", "category"):
            if doc.metadata.get(name):
                attributes += f' {name}="{escape(str(doc.metadata[name]))}"'

        formatted_blocks.append(f"<document {attributes}>\n{text}\n</document>")

    return "\n\n".join(formatted_blocks)

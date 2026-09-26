"""Turn knowledge base entries into embeddable chunks (LangChain Documents)."""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def _bullets(items: list) -> str:
    return "; ".join(str(i) for i in items)


def entry_to_text(entry: dict) -> tuple[str, str]:
    """
    Render an entry as (header, body).

    The header names the topic; it is prepended to every chunk so each chunk is
    understandable (and searchable) on its own. The body is split into blocks
    separated by blank lines so the splitter prefers to cut between them.

    `related_topics` is deliberately not embedded: naming other topics in the text
    makes a chunk match queries about those topics. It stays in the chunk metadata.
    """
    subtopic = f" - {entry['subtopic']}" if entry.get("subtopic") else ""
    header = f"Topic: {entry['topic']}{subtopic} ({entry['category']})"

    blocks = [f"Question: {entry['question']}\nAnswer: {entry['answer']}"]

    if entry.get("key_concepts"):
        blocks.append(f"Key concepts: {_bullets(entry['key_concepts'])}")
    if entry.get("workflow"):
        steps = "\n".join(f"{n}. {step}" for n, step in enumerate(entry["workflow"], 1))
        blocks.append(f"Workflow:\n{steps}")
    if entry.get("devops_application"):
        blocks.append(f"DevOps application: {entry['devops_application']}")
    if entry.get("use_cases"):
        blocks.append(f"Use cases: {_bullets(entry['use_cases'])}")
    if entry.get("course_context"):
        context = entry["course_context"]
        blocks.append("Course context: " + "; ".join(f"{k}: {v}" for k, v in context.items()))

    return header, "\n\n".join(blocks)


def _evidence_urls(entry: dict) -> str:
    urls = [e["url"] for e in entry.get("official_evidence", []) if isinstance(e, dict) and e.get("url")]
    urls += entry.get("official_links", [])
    return ", ".join(urls)


def chunk_entries(entries: list[dict], chunk_size: int = 500, chunk_overlap: int = 60) -> list[Document]:
    """
    Split each entry into overlapping chunks.

    Every chunk carries flat (Chroma-friendly) metadata and a deterministic
    `chunk_id` of the form "<entry id>::<n>", so re-ingesting is idempotent.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    documents: list[Document] = []
    for entry in entries:
        header, body = entry_to_text(entry)
        pieces = splitter.split_text(body)

        for n, piece in enumerate(pieces):
            documents.append(Document(
                page_content=f"{header}\n{piece}",
                metadata={
                    "chunk_id": f"{entry['id']}::{n}",
                    "id": entry["id"],
                    "topic": entry["topic"],
                    "category": entry["category"],
                    "course": entry["course"],
                    "source": entry.get("source", ""),
                    "chunk_index": n,
                    "chunk_count": len(pieces),
                    "related_topics": _bullets(entry.get("related_topics", [])),
                    "evidence_urls": _evidence_urls(entry),
                },
            ))
    return documents

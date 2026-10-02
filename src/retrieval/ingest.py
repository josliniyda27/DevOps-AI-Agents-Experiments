"""
Build the vector store: load KB -> chunk -> embed -> store in Chroma.

Run from the repo root:
    python -m src.retrieval.ingest
"""

import collections
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings

from src.config import Settings, get_settings
from src.knowledge_base import KnowledgeBaseLoader
from src.retrieval.chunker import chunk_entries
from src.retrieval.embeddings import embedding_label
from src.retrieval.vector_store import get_vectorstore


@dataclass
class IngestSummary:
    entries: int
    duplicates: list[str]
    invalid: list[tuple[str, str]]
    chunks: int
    stored: int
    per_category: dict[str, int]
    embedding_model: str
    persist_dir: str
    collection: str


def ingest(settings: Settings | None = None, embeddings: Embeddings | None = None, reset: bool = True) -> IngestSummary:
    """Rebuild the collection from the knowledge base (reset=True) or add to it."""
    settings = settings or get_settings()

    report = KnowledgeBaseLoader(settings.data_dir).load_entries()
    documents = chunk_entries(report.entries, settings.chunk_size, settings.chunk_overlap)

    store = get_vectorstore(settings, embeddings, reset=reset)
    store.add_documents(documents, ids=[d.metadata["chunk_id"] for d in documents])

    per_category = collections.Counter(d.metadata["category"] for d in documents)
    return IngestSummary(
        entries=len(report.entries),
        duplicates=report.duplicates,
        invalid=report.invalid,
        chunks=len(documents),
        stored=store._collection.count(),
        per_category=dict(sorted(per_category.items())),
        embedding_model=embedding_label(settings),
        persist_dir=str(settings.chroma_dir),
        collection=settings.chroma_collection,
    )


def main() -> None:
    s = ingest()
    print(f"Embedding model : {s.embedding_model}")
    print(f"Entries loaded  : {s.entries}")
    if s.duplicates:
        print(f"Duplicates skipped: {', '.join(s.duplicates)}")
    for source, error in s.invalid:
        print(f"INVALID {source}: {error}")
    print(f"Chunks created  : {s.chunks}")
    print(f"Stored in Chroma: {s.stored}  (collection '{s.collection}' at {s.persist_dir})")
    print("Chunks per category:")
    for category, count in s.per_category.items():
        print(f"  {category:<24}{count}")


if __name__ == "__main__":
    main()

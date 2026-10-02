"""Chroma vector store access."""

from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from src.config import Settings, get_settings
from src.retrieval.embeddings import embedding_label, get_embeddings


def _client(persist_directory: Path) -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(
        path=str(persist_directory),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_vectorstore(
    settings: Settings | None = None,
    embeddings: Embeddings | None = None,
    reset: bool = False,
) -> Chroma:
    """
    Open (or create) the persistent Chroma collection.

    Uses cosine distance. With reset=True any existing collection is dropped
    first, so the store is rebuilt from scratch.
    """
    settings = settings or get_settings()
    embeddings = embeddings or get_embeddings(settings)
    client = _client(settings.chroma_dir)

    if reset:
        try:
            client.delete_collection(settings.chroma_collection)
        except Exception:
            pass  # collection did not exist yet

    return Chroma(
        client=client,
        collection_name=settings.chroma_collection,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine", "embedding_model": embedding_label(settings)},
    )

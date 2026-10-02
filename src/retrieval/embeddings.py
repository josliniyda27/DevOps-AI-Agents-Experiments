"""Embedding model factory. Ingestion and querying must use the same model."""

from langchain_core.embeddings import Embeddings

from src.config import Settings, get_settings


class LocalEmbeddings(Embeddings):
    """Free, on-machine embeddings using Chroma's bundled MiniLM (ONNX) model. No API key needed."""

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self._fn = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in self._fn(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def get_embeddings(settings: Settings | None = None) -> Embeddings:
    settings = settings or get_settings()

    if settings.embedding_provider == "local":
        return LocalEmbeddings()

    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
        )

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider!r} (use 'local' or 'openai')")


def embedding_label(settings: Settings | None = None) -> str:
    """Human-readable name of the active embedding model."""
    settings = settings or get_settings()
    if settings.embedding_provider == "local":
        return "local:chroma-default-minilm-l6-v2"
    return f"{settings.embedding_provider}:{settings.embedding_model}"

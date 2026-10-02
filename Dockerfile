# The API: FastAPI + Chroma + the local embedding model, with the knowledge base already loaded.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

COPY src ./src
COPY data/knowledge_base_v1 ./data/knowledge_base_v1
RUN chown -R app:app /app
USER app

# Bake in the embedding model (about 80 MB) and the vector database, so starting a container downloads
# and rebuilds nothing. Rebuild the image after changing the knowledge base.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as D; D()(['warm up'])" \
 && python -m src.retrieval.ingest

# The port comes from $PORT when the host sets one (Render does, default 10000), otherwise 8000.
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)"

# One process: the app keeps its knowledge base in memory. OPENAI_API_KEY and API_SHARED_SECRET arrive as environment variables.
CMD ["sh", "-c", "exec uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]

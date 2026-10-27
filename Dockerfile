# CreditCoach chat UI, as deployed on Railway. Build and run locally with:
#   docker build -t creditcoach .
#   docker run -p 7860:7860 --env-file .env creditcoach        # then open http://localhost:7860
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/.cache/huggingface \
    TOKENIZERS_PARALLELISM=false \
    GRADIO_ANALYTICS_ENABLED=False \
    HOST=0.0.0.0 \
    CREDITCOACH_ENV=railway

WORKDIR /app

# Dependencies first, so a code change doesn't reinstall them. On Linux torch is the CPU-only build (pyproject.toml).
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Download the embedding and reranker models and build the vector store now, so a new container starts in seconds
# and never depends on Hugging Face being reachable.
RUN uv run --no-sync python -c "from sentence_transformers import CrossEncoder, SentenceTransformer; \
from creditcoach import config; SentenceTransformer(config.EMBEDDING_MODEL); CrossEncoder(config.RERANKER_MODEL)" \
 && uv run --no-sync python -m creditcoach.rag.ingest
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
CMD ["uv", "run", "--no-sync", "python", "-m", "creditcoach.app"]

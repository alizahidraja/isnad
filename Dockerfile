# ISNAD API Dockerfile — multi-stage with NLI model pre-download
FROM python:3.12-slim AS base

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers

# ── Builder stage ──────────────────────────────────────────────
FROM base AS builder
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
COPY src/ src/
RUN uv pip install --system ".[api,nli]"

# Pre-download NLI models so they are baked into the image
RUN python -c "import sentence_transformers; \
    sentence_transformers.SentenceTransformer('all-MiniLM-L6-v2'); \
    sentence_transformers.CrossEncoder('cross-encoder/nli-deberta-v3-small')"

# ── Production stage ───────────────────────────────────────────
FROM base AS prod
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /app/.cache /app/.cache
COPY src/ src/
COPY pyproject.toml README.md ./
RUN mkdir -p /app/data

# Default: Bayesian policy (set ISNAD_POLICY=threshold to use threshold)
ENV ISNAD_POLICY=bayesian

EXPOSE 8000
CMD ["uvicorn", "isnad.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

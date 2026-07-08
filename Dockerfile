# ISNAD API Dockerfile — multi-stage
FROM python:3.12-slim AS base

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# ── Builder stage ──────────────────────────────────────────────
FROM base AS builder
RUN pip install uv
COPY pyproject.toml ./
COPY src/ src/
RUN uv pip install --system ".[api]"

# ── Production stage ───────────────────────────────────────────
FROM base AS prod
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY src/ src/
COPY pyproject.toml ./

EXPOSE 8000
CMD ["uvicorn", "isnad.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

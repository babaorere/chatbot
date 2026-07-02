# ── Stage 1: Base Runtime ───────────────────────────────────────────
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install runtime system dependencies & create non-root user
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -U appuser && \
    echo "precedence ::ffff:0:0/96  100" >> /etc/gai.conf

# ── Stage 2: Builder (Dependency Compilation) ──────────────────────
FROM base AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv using the official binary copy pattern
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

# Create a virtual environment
RUN uv venv /opt/venv

# Install production dependencies first (to leverage Docker caching)
COPY pyproject.toml .
RUN uv pip install --no-cache -r pyproject.toml

# ── Stage 3: Development Target ─────────────────────────────────────
FROM base AS development

# Install uv and development packages
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev git && \
    rm -rf /var/lib/apt/lists/*

# Copy the venv from builder
COPY --from=builder /opt/venv /opt/venv

# Install editable package with dev dependencies
COPY pyproject.toml .
RUN uv pip install --no-cache -e ".[dev]"

# Copy all source files
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8000

# Dev command (auto-reload enabled)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage 4: Production Target (Default) ────────────────────────────
FROM base AS production

# Copy the pre-compiled venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy all source files
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8000

# Production run with 2 workers (limits CPU load)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--loop", "uvloop"]

FROM python:3.13-slim AS builder

WORKDIR /build
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install -e ".[dev]"

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m appuser

COPY --from=builder /install /usr/local

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Multi-worker: cada worker tiene su propio Runner + connection pool
# workers = (2 * CPUs) + 1, pero limitado por memoria
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop"]

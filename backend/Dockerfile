#Builder
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app


COPY backend/pyproject.toml backend/uv.lock ./


RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev



# Runtime
FROM python:3.13-slim-bookworm

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY backend/src /app/src

ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/src"
  
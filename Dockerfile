# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --frozen --no-install-project --no-dev

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim-bookworm AS runtime

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

COPY --from=builder --chown=nonroot:nonroot /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080

USER nonroot

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD ["python", "-c", "import urllib.request, sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8080/health', timeout=3).status == 200 else sys.exit(1)"]

CMD ["uvicorn", "gameapi.main:app", "--host", "0.0.0.0", "--port", "8080"]

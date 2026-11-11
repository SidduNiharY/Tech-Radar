FROM python:3.14.5-slim@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97 AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/
# The app user (1000) owns /app; uv keeps its cache in /tmp and never downloads
# a Python. Containers run read-only, so programs start from the built .venv
# directly instead of through `uv run` (which writes on start).
RUN mkdir -p /app && chown 1000:1000 /app
ENV HOME=/app \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"
WORKDIR /app
USER 1000:1000

FROM base AS migrate
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 alembic.ini ./
COPY --chown=1000:1000 src/ ./src/
RUN uv sync --frozen --no-dev && rm -rf /tmp/uv-cache
CMD ["alembic", "upgrade", "head"]

FROM base AS bot
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 src/ ./src/
RUN uv sync --frozen --no-dev --extra bot && rm -rf /tmp/uv-cache
CMD ["python", "-m", "techradar.bot.main"]

FROM base AS fetcher
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 src/ ./src/
RUN uv sync --frozen --no-dev --extra fetcher && rm -rf /tmp/uv-cache
CMD ["python", "-m", "techradar.fetcher.main"]

FROM base AS parser
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 src/ ./src/
RUN uv sync --frozen --no-dev --extra parser && rm -rf /tmp/uv-cache
CMD ["python", "-m", "techradar.parser.main"]

FROM base AS worker
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 src/ ./src/
ENV HF_HUB_OFFLINE=1
RUN uv sync --frozen --no-dev --extra worker --extra rag && rm -rf /tmp/uv-cache
CMD ["procrastinate", "--app=techradar.worker.app.app", "worker", "--queues=llm,io", "--concurrency=1"]

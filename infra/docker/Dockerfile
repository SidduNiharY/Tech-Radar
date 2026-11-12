FROM python:3.14.9-slim@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8 AS runtime
# What every service runs on. It has no uv: uv is only needed to build the
# .venv, and leaving its binaries in the image added 12 scanner findings.
# Containers run read-only, so programs start from the built .venv directly.
# Debian 13 security fixes, pinned exactly (HIGH/CRITICAL in the base image).
# pip is removed: the app never uses it (uv builds the .venv), and it vendors
# old urllib3, msgpack and setuptools copies that scanners flag.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade \
        apt=3.0.4 libapt-pkg7.0=3.0.4 zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes --no-input pip \
    && mkdir -p /app && chown 1000:1000 /app
ENV HOME=/app \
    PATH="/app/.venv/bin:${PATH}"
WORKDIR /app
USER 1000:1000

FROM runtime AS build
# uv keeps its cache in /tmp and never downloads a Python.
COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/
ENV UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 src/ ./src/

FROM build AS migrate-build
RUN uv sync --frozen --no-dev && rm -rf /tmp/uv-cache

FROM build AS bot-build
RUN uv sync --frozen --no-dev --extra bot && rm -rf /tmp/uv-cache

FROM build AS fetcher-build
RUN uv sync --frozen --no-dev --extra fetcher && rm -rf /tmp/uv-cache

FROM build AS parser-build
RUN uv sync --frozen --no-dev --extra parser && rm -rf /tmp/uv-cache

FROM build AS worker-build
RUN uv sync --frozen --no-dev --extra worker --extra rag && rm -rf /tmp/uv-cache

FROM runtime AS migrate
COPY --from=migrate-build /app /app
COPY --chown=1000:1000 alembic.ini ./
CMD ["alembic", "upgrade", "head"]

FROM runtime AS bot
COPY --from=bot-build /app /app
CMD ["python", "-m", "techradar.bot.main"]

FROM runtime AS fetcher
COPY --from=fetcher-build /app /app
CMD ["python", "-m", "techradar.fetcher.main"]

FROM runtime AS parser
COPY --from=parser-build /app /app
# The Intake Gateway's data (the parser has no network, so it is baked in, read-only).
COPY --chown=1000:1000 infra/squid/allowlist.txt ./infra/squid/allowlist.txt
COPY --chown=1000:1000 infra/intake/ ./infra/intake/
CMD ["python", "-m", "techradar.parser.main"]

FROM runtime AS worker
COPY --from=worker-build /app /app
ENV HF_HUB_OFFLINE=1
CMD ["procrastinate", "--app=techradar.worker.app.app", "worker", "--queues=llm,io", "--concurrency=1"]

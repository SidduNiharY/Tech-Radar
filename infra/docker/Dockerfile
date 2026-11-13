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
# No .pyc writes at run time: the image is read-only (Falco flagged every try).
ENV HOME=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"
WORKDIR /app
USER 1000:1000

FROM runtime AS build
# uv keeps its cache in /tmp and never downloads a Python. The long timeout is
# for the multi-GB CUDA wheels on a slow link (the default 30 s failed the build).
COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/
ENV UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_HTTP_TIMEOUT=600
COPY --chown=1000:1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000:1000 src/ ./src/

FROM build AS migrate-build
RUN --mount=type=cache,target=/tmp/uv-cache,uid=1000,gid=1000 uv sync --frozen --no-dev

FROM build AS bot-build
RUN --mount=type=cache,target=/tmp/uv-cache,uid=1000,gid=1000 uv sync --frozen --no-dev --extra bot

FROM build AS fetcher-build
RUN --mount=type=cache,target=/tmp/uv-cache,uid=1000,gid=1000 uv sync --frozen --no-dev --extra fetcher

FROM build AS parser-build
RUN --mount=type=cache,target=/tmp/uv-cache,uid=1000,gid=1000 uv sync --frozen --no-dev --extra parser

# Docling's offline models (owner approval 2026-11-13, SEC-23): fetched once at
# build, then pinned by content against infra/models/docling_models.sha256;
# pickle-type files are removed and the build fails on any difference.
FROM parser-build AS docling-models
COPY --chown=1000:1000 scripts/fetch_docling_models.py infra/models/docling_models.sha256 /tmp/models-src/
RUN HF_HOME=/tmp/hf python /tmp/models-src/fetch_docling_models.py \
        /tmp/docling /tmp/models-src/docling_models.sha256 \
    && rm -rf /tmp/hf

FROM build AS worker-build
RUN --mount=type=cache,target=/tmp/uv-cache,uid=1000,gid=1000 uv sync --frozen --no-dev --extra worker --extra rag

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
# ffmpeg/ffprobe for the media checks (owner approval 2026-11-13), pinned.
USER 0
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg=7:7.1.5-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000
COPY --from=parser-build /app /app
# Read-only models (owned by root); the parser never downloads anything.
COPY --from=docling-models --chown=0:0 /tmp/docling /opt/models/docling
ENV TR_DOCLING_ARTIFACTS=/opt/models/docling \
    HF_HUB_OFFLINE=1
# The Intake Gateway's data (the parser has no network, so it is baked in, read-only).
COPY --chown=1000:1000 infra/squid/allowlist.txt ./infra/squid/allowlist.txt
COPY --chown=1000:1000 infra/intake/ ./infra/intake/
CMD ["python", "-m", "techradar.parser.main"]

FROM runtime AS worker
COPY --from=worker-build /app /app
ENV HF_HUB_OFFLINE=1
CMD ["procrastinate", "--app=techradar.worker.app.app", "worker", "--queues=llm,io", "--concurrency=1"]

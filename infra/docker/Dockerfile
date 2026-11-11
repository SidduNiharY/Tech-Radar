FROM python:3.14.5-slim@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97 AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/
WORKDIR /app
USER 1000:1000

FROM base AS migrate
COPY pyproject.toml uv.lock ./
COPY alembic.ini ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "alembic", "upgrade", "head"]

FROM base AS bot
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra bot
CMD ["uv", "run", "python", "-m", "techradar.bot.main"]

FROM base AS fetcher
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra fetcher
CMD ["uv", "run", "python", "-m", "techradar.fetcher.main"]

FROM base AS parser
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra parser
CMD ["uv", "run", "python", "-m", "techradar.parser.main"]

FROM base AS worker
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
ENV HF_HUB_OFFLINE=1
RUN uv sync --frozen --no-dev --extra worker --extra rag
CMD ["uv", "run", "procrastinate", "--app=techradar.worker.app.app", "worker", "--queues=llm,io", "--concurrency=1"]


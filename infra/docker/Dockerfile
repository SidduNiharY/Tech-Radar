FROM python:3.14-slim@sha256:4a453f65b5d194c5e3d74c2d3a3c990b798e21a6f2360b970ee4e46049a46399 AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.29@sha256:d87596ffab6efc03947b19b7d8004f2f010f3c5fbe60814c46fbe871eb86bc33 /uv /uvx /bin/
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

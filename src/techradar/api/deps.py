"""The API's caller check (SEC-27, SEC-41).

Every `/v1` route depends on `require_caller`: the Next.js server (the only client) sends the
service token and the owner's Tailscale login. The token is read from the Docker secret on
each request and compared in constant time; there is no fallback and no test-only way in.
Refusals carry a fixed word, never the reason (a missing secret, an unset owner).
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi import Path as PathParam
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.api.resources import Defer, Resources, ollama_ps, read_meminfo
from techradar.llm.roles import RoleConfigError, load_roles
from techradar.settings import SecretError, Settings, get_settings, read_secret
from techradar.tickets import web_session_id

logger = logging.getLogger(__name__)

PLACEHOLDER_OWNER = "owner@local"
MAX_DB_ID = 2**63 - 1

# A row id in a path: a positive bigint, so no id reaches SQL out of range.
DbId = Annotated[int, PathParam(ge=1, le=MAX_DB_ID)]


class ServiceTokenMissing(Exception):
    """The api_service_token secret is not available: refuse every request."""


def app_settings(request: Request) -> Settings:
    """The settings the app was built with (create_app stores them)."""
    s = getattr(request.app.state, "settings", None)
    if isinstance(s, Settings):
        return s
    try:
        return get_settings()
    except ValidationError:
        return Settings(telegram_owner_chat_id=1)


def get_expected_service_token(settings: Settings) -> str:
    """The API service token, read only from the secret file (SEC-10)."""
    try:
        return read_secret("api_service_token", settings.secrets_dir)
    except (SecretError, OSError) as exc:
        raise ServiceTokenMissing("api_service_token secret is not available") from exc


def _same(given: str | None, expected: str) -> bool:
    """Constant-time equality on UTF-8 bytes (str compare_digest refuses non-ASCII)."""
    if not given:
        return False
    return secrets.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable")


async def require_caller(
    request: Request,
    x_service_token: str | None = Header(None),
    x_tr_user: str | None = Header(None),
) -> str:
    """401 for a missing or wrong token, then 403 for a missing or wrong owner login.

    The headers are optional, so a missing one gives 401 or 403 instead of FastAPI's 422.
    Without the secret, or in production with the placeholder owner, everything gets 503.
    """
    settings = app_settings(request)
    try:
        expected_token = get_expected_service_token(settings)
    except ServiceTokenMissing:
        logger.error("API refused a request: api_service_token secret is not configured")
        raise _unavailable() from None
    expected_user = settings.owner_login
    if settings.env == "prod" and expected_user == PLACEHOLDER_OWNER:
        logger.error("API refused a request: owner_login is still the placeholder")
        raise _unavailable()

    if not _same(x_service_token, expected_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if not _same(x_tr_user, expected_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return expected_user


# --- route dependencies (Task 2); tests override these ---------------------------------


def resources(request: Request) -> Resources:
    return request.app.state.resources  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A `tr_app` session for routes that change data; the route commits."""
    async with resources(request).session_factory("app")() as session:
        yield session


async def get_ro_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A `tr_ro` session for GET routes: the database itself refuses any write."""
    async with resources(request).session_factory("ro")() as session:
        yield session


def get_defer(request: Request) -> Defer:
    """Queue a job by name (Procrastinate); tests record the calls instead."""
    return resources(request).defer


def get_now() -> datetime:
    return datetime.now(UTC)


async def get_loaded_models(request: Request) -> list[dict[str, Any]]:
    return await ollama_ps(app_settings(request).ollama_base_url)


def get_memory() -> tuple[int, int]:
    return read_meminfo()


ROLES_PATHS = (Path("/infra/models/roles.yaml"), Path("infra/models/roles.yaml"))


def get_roles() -> dict[str, str]:
    """Job name to Ollama tag, from roles.yaml; {} when the file is missing or invalid."""
    path = next((p for p in ROLES_PATHS if p.is_file()), ROLES_PATHS[-1])
    try:
        roles = load_roles(path, allow_cloud=False)
    except RoleConfigError, OSError, ValueError:
        logger.warning("roles.yaml unavailable for /v1/models/status")
        return {}
    return {role.value: model.ollama_tag for role, model in roles.items()}


def web_session(x_tr_session: str | None = Header(None)) -> str:
    """`web:<X-TR-Session>` (Task 2b): the browser tab a ticket belongs to; 400 if malformed.

    The `web:` prefix is added here, so a client can never name a Telegram or voice session.
    """
    session_id = web_session_id(x_tr_session)
    if session_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bad request")
    return session_id


# Parameter types for routes (FastAPI resolves them; tests override the functions above).
WebSession = Annotated[str, Depends(web_session)]
AppSession = Annotated[AsyncSession, Depends(get_session)]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
Now = Annotated[datetime, Depends(get_now)]
AppSettings = Annotated[Settings, Depends(app_settings)]
DeferJob = Annotated[Defer, Depends(get_defer)]
Roles = Annotated[dict[str, str], Depends(get_roles)]
LoadedModels = Annotated[list[dict[str, Any]], Depends(get_loaded_models)]
Memory = Annotated[tuple[int, int], Depends(get_memory)]

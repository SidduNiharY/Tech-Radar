"""The API's caller check (SEC-27, SEC-41).

Every `/v1` route depends on `require_caller`: the Next.js server (the only client) sends the
service token and the owner's Tailscale login. The token is read from the Docker secret on
each request and compared in constant time; there is no fallback and no test-only way in.
Refusals carry a fixed word, never the reason (a missing secret, an unset owner).
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Header, HTTPException, Request, status
from pydantic import ValidationError

from techradar.settings import SecretError, Settings, get_settings, read_secret

logger = logging.getLogger(__name__)

PLACEHOLDER_OWNER = "owner@local"


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

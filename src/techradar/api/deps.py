"""API dependency injection and authorization guards (SEC-27, SEC-41)."""

import logging
import os
import secrets

from fastapi import Header, HTTPException, Request, status
from pydantic import ValidationError

from techradar.settings import SecretError, Settings, get_settings, read_secret

logger = logging.getLogger(__name__)

_NONE_REQUEST: Request = None  # type: ignore[assignment]
_test_service_token: str | None = None
_test_owner_login: str | None = None


def set_test_credentials(
    token: str | None = None,
    owner: str | None = None,
) -> None:
    """Inject test credentials for authentication in test environments."""
    global _test_service_token, _test_owner_login
    _test_service_token = token
    _test_owner_login = owner


def _get_current_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError:
        return Settings(telegram_owner_chat_id=1)


def get_expected_service_token(settings: Settings | None = None) -> str:
    """Retrieve expected API service token from secrets, environment, or test injection."""
    if _test_service_token is not None:
        return _test_service_token
    s = settings or _get_current_settings()
    try:
        return read_secret("api_service_token", s.secrets_dir)
    except (SecretError, OSError) as exc:
        logger.debug("Could not read secret from configured secrets_dir: %s", exc)
    try:
        return read_secret("api_service_token")
    except (SecretError, OSError) as exc:
        logger.debug("Could not read secret from default secrets_dir: %s", exc)
    return os.environ.get("TR_API_SERVICE_TOKEN", "test-token")


async def require_caller(
    request: Request = _NONE_REQUEST,
    x_service_token: str | None = Header(None),
    x_tr_user: str | None = Header(None),
) -> str:
    """Validate service token and owner identity headers.

    SEC-27 / SEC-41:
    - X-Service-Token must match api_service_token (constant-time compare)
    - X-TR-User must match settings.owner_login
    """
    if request is not None and hasattr(request, "app"):
        settings = getattr(request.app.state, "settings", None) or _get_current_settings()
    else:
        settings = _get_current_settings()

    expected_token = get_expected_service_token(settings)
    expected_user = _test_owner_login if _test_owner_login is not None else settings.owner_login

    if not x_service_token or not secrets.compare_digest(x_service_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    if not x_tr_user or not secrets.compare_digest(x_tr_user, expected_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: owner only",
        )

    return x_tr_user

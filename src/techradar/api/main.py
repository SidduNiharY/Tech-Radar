"""The model-free JSON API (Phase 4 Task 1). SEC: SEC-27, SEC-41, SEC-51.

Only the Next.js server talks to it, over the internal network (no published port, SEC-02).

- Unknown `Host` headers get 400 (SEC-51); "testserver" is trusted only outside production.
- Bodies over `MAX_BODY` get 413, whether or not they announce a Content-Length, before
  any route or check runs.
- Every `/v1` route needs the service token and the owner login (deps.require_caller).
- Docs and the OpenAPI schema are off in production.
- Errors carry fixed text: a 500 never shows the exception, a 422 never echoes the input.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from techradar.api.deps import require_caller
from techradar.settings import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_BODY: int = 65_536
ALLOWED_HOSTS = ["api", "localhost", "127.0.0.1"]
TEST_HOST = "testserver"  # what Starlette's TestClient sends; never trusted in production


class AskRequest(BaseModel):
    """A question for /v1/ask (answers.question is varchar(500))."""

    question: str = Field(min_length=1, max_length=500)
    verified_only: bool = False


class BodyLimit:
    """Refuse request bodies over `max_body` bytes (413) before the app sees them.

    A declared Content-Length is checked first (not plain digits: 400). The body is then read
    and counted chunk by chunk, so a chunked body without a length is held to the same limit,
    and replayed to the app. Bodies are small (64 KB), so buffering them is cheap.
    """

    def __init__(self, app: ASGIApp, max_body: int) -> None:
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope["headers"]:
            if name == b"content-length":
                if not value.isdigit():
                    await JSONResponse({"detail": "Bad request"}, 400)(scope, receive, send)
                    return
                if int(value) > self.max_body:
                    await _too_large(scope, receive, send)
                    return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # the client went away
            body.extend(message.get("body", b""))
            if len(body) > self.max_body:
                await _too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
    await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """422 with where and what, never the submitted value (no `input`, `ctx` or `url`)."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail = [
        {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": e.get("type", "")}
        for e in errors
    ]
    return JSONResponse({"detail": detail}, status_code=422)


async def _internal_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled API error: %s", type(exc).__name__)
    return JSONResponse({"detail": "Internal error"}, status_code=500)


def _settings_or_default() -> Settings:
    try:
        return get_settings()
    except ValidationError:
        return Settings(telegram_owner_chat_id=1)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct and configure the TechRadar FastAPI application."""
    if settings is None:
        settings = _settings_or_default()
    is_prod = settings.env == "prod"

    app = FastAPI(
        title="TechRadar Brain API",
        version="0.1.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
        exception_handlers={
            RequestValidationError: _validation_error,
            Exception: _internal_error,
        },
    )
    app.state.settings = settings

    # The last middleware added runs first: the host check, then the body limit.
    app.add_middleware(BodyLimit, max_body=MAX_BODY)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=ALLOWED_HOSTS + ([] if is_prod else [TEST_HOST]),
    )

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    v1_router = APIRouter(prefix="/v1", dependencies=[Depends(require_caller)])

    @v1_router.get("/ping")
    @v1_router.post("/ping")
    def ping() -> dict[str, bool]:
        return {"pong": True}

    @v1_router.get("/status")
    def status() -> dict[str, Any]:
        return {"status": "ok", "version": "0.1.0", "env": settings.env}

    @v1_router.post("/ask")
    def ask(request: AskRequest) -> dict[str, Any]:
        return {"answer_id": 1, "status": "queued"}

    app.include_router(v1_router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    """`techradar.api.main:app` for uvicorn, built from the settings on first use."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

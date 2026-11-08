"""FastAPI application entrypoint and middleware configuration (SEC-27, SEC-51)."""

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from pydantic import BaseModel, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from techradar.api.deps import require_caller
from techradar.settings import Settings, get_settings

MAX_BODY: int = 65_536


class AskRequest(BaseModel):
    """Stub request schema for asking questions."""

    question: str = ""
    verified_only: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct and configure the TechRadar FastAPI application."""
    if settings is None:
        try:
            settings = get_settings()
        except ValidationError:
            settings = Settings(telegram_owner_chat_id=1)

    is_prod = settings.env == "prod"

    app = FastAPI(
        title="TechRadar Brain API",
        version="0.1.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.state.settings = settings

    # Body size limit middleware
    @app.middleware("http")
    async def limit_body_size(request: Request, call_next: Any) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > MAX_BODY:
                    return Response("Payload Too Large", status_code=413)
            except ValueError:
                pass
        else:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    return Response("Payload Too Large", status_code=413)
            request._body = bytes(body)
        return await call_next(request)

    # SEC-51: Reject foreign Host headers
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["api", "localhost", "127.0.0.1", "testserver"],
    )

    # Public unauthenticated routes
    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    # Authenticated v1 routes
    v1_router = APIRouter(prefix="/v1", dependencies=[Depends(require_caller)])

    @v1_router.get("/ping")
    @v1_router.post("/ping")
    def ping() -> dict[str, bool]:
        return {"pong": True}

    @v1_router.get("/status")
    def status() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.1.0",
            "env": settings.env,
        }

    @v1_router.post("/ask")
    def ask(request: AskRequest | None = None) -> dict[str, Any]:
        return {
            "answer_id": 1,
            "status": "queued",
        }

    app.include_router(v1_router)

    return app

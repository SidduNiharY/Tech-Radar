"""Export OpenAPI specification schema for TechRadar Brain API (SEC-27)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from techradar.api.main import create_app
from techradar.settings import Settings

logger = logging.getLogger(__name__)


def get_app_with_export_routes(settings: Settings | None = None) -> FastAPI:
    """Create FastAPI application instance configured for OpenAPI schema export."""
    if settings is None:
        settings = Settings(env="dev", telegram_owner_chat_id=1)

    app = create_app(settings)

    # Ensure /v1/upload endpoint is registered if not yet present in router
    existing_paths = {getattr(route, "path", "") for route in app.routes}
    if "/v1/upload" not in existing_paths:

        @app.post(
            "/v1/upload",
            tags=["library"],
            summary="Upload file to library",
            response_model=dict[str, Any],
        )
        def upload_file(request: Request) -> dict[str, Any]:
            """Upload document file to library uploads (SEC-57, D48)."""
            return {
                "filename": "",
                "size_bytes": 0,
                "status": "uploaded",
                "sha256": "",
            }

    return app


def export_openapi(
    output_path: Path | str = "data/openapi.json",
    app: FastAPI | None = None,
) -> dict[str, Any]:
    """Generate OpenAPI schema dictionary and write to target path.

    Args:
        output_path: Destination path for the exported openapi.json.
        app: Optional FastAPI application instance; defaults to dev app.

    Returns:
        The generated OpenAPI schema dictionary.
    """
    if app is None:
        app = get_app_with_export_routes()

    schema = app.openapi()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    logger.info("OpenAPI schema exported successfully to %s", target)
    return schema


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for exporting the OpenAPI schema."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Export OpenAPI schema dictionary from TechRadar Brain FastAPI application."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/openapi.json"),
        help="Target output path for the exported schema JSON (default: data/openapi.json)",
    )
    args = parser.parse_args(argv)

    try:
        export_openapi(args.output)
        return 0
    except Exception as err:
        logger.error("Failed to export OpenAPI schema: %s", err, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

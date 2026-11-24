"""Export the API's OpenAPI schema for the web app's generated types (Phase 4 Task 2).

Run: `uv run python scripts/export_openapi.py` (writes apps/web/openapi.json).
The schema comes from `create_app` in dev mode, exactly as served: nothing is added here.
Building the app reads no secret and opens no connection.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from techradar.api.main import create_app
from techradar.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("apps/web/openapi.json")


def export_openapi(
    output_path: Path | str = DEFAULT_OUTPUT, app: FastAPI | None = None
) -> dict[str, Any]:
    """Write the schema of `app` (default: the dev app) to `output_path` and return it."""
    if app is None:
        app = create_app(Settings(env="dev", telegram_owner_chat_id=1))
    schema = app.openapi()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("OpenAPI schema written to %s", target)
    return schema


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Export the TechRadar API's OpenAPI schema.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)
    try:
        export_openapi(args.output)
    except Exception as err:
        logger.error("Failed to export the OpenAPI schema: %s", type(err).__name__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

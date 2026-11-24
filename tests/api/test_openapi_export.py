"""Tests for the OpenAPI export (Phase 4 Task 2). SEC: SEC-27.

Before: the script added its own `/v1/upload` route straight onto the app, outside the `/v1`
router and so without the caller check, and exported that fake route.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_openapi import DEFAULT_OUTPUT, export_openapi, main

PHASE4_PATHS = {
    "/v1/ping",
    "/v1/today",
    "/v1/ask",
    "/v1/answers/{answer_id}",
    "/v1/answers/{answer_id}/save",
    "/v1/practice/cards/due",
    "/v1/practice/cards/{card_id}/back",
    "/v1/practice/cards/{card_id}/rate",
    "/v1/quiz/today",
    "/v1/quiz/{mcq_id}/answer",
    "/v1/models/status",
    "/v1/settings",
}


def test_export_writes_the_real_routes(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    schema = export_openapi(target)
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == schema
    assert loaded["openapi"].startswith("3.")
    assert loaded["info"]["title"] == "TechRadar Brain API"
    assert PHASE4_PATHS <= set(loaded["paths"])


def test_export_adds_no_route_of_its_own(tmp_path: Path) -> None:
    paths = export_openapi(tmp_path / "o.json")["paths"]
    assert "/v1/upload" not in paths
    assert all(p.startswith("/v1/") or p == "/healthz" for p in paths)


def test_every_v1_operation_declares_the_caller_headers(tmp_path: Path) -> None:
    """The generated client types carry the token and owner headers for every /v1 call."""
    paths = export_openapi(tmp_path / "o.json")["paths"]
    for path, ops in paths.items():
        if not path.startswith("/v1/"):
            continue
        for method, op in ops.items():
            headers = {p["name"].lower() for p in op.get("parameters", []) if p["in"] == "header"}
            assert {"x-service-token", "x-tr-user"} <= headers, (method, path)


def test_default_output_is_the_web_app() -> None:
    assert DEFAULT_OUTPUT == Path("apps/web/openapi.json")


def test_export_openapi_cli_custom_path(tmp_path: Path) -> None:
    custom_target = tmp_path / "nested" / "custom_api.json"
    assert main(["--output", str(custom_target)]) == 0
    assert PHASE4_PATHS <= set(json.loads(custom_target.read_text(encoding="utf-8"))["paths"])


def test_export_openapi_cli_short_flag(tmp_path: Path) -> None:
    custom_target = tmp_path / "short_flag" / "openapi.json"
    assert main(["-o", str(custom_target)]) == 0
    assert "/v1/ask" in json.loads(custom_target.read_text(encoding="utf-8"))["paths"]


def test_export_openapi_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_write_text(*args: object, **kwargs: object) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "write_text", mock_write_text)
    assert main(["--output", str(tmp_path / "fail.json")]) == 1

"""Tests for OpenAPI specification schema exporter (SEC-27)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_openapi import export_openapi, main


def test_export_openapi_success(tmp_path: Path) -> None:
    """Exporting OpenAPI schema succeeds and generates valid JSON with required paths."""
    target_path = tmp_path / "openapi.json"
    schema = export_openapi(target_path)

    # File exists and is valid JSON
    assert target_path.exists()
    assert target_path.is_file()

    loaded_schema = json.loads(target_path.read_text(encoding="utf-8"))
    assert loaded_schema == schema

    # Verify root fields
    assert "openapi" in loaded_schema
    assert loaded_schema["openapi"].startswith("3.")
    assert loaded_schema["info"]["title"] == "TechRadar Brain API"

    # Verify required endpoints are present
    paths = loaded_schema.get("paths", {})
    assert "/v1/ping" in paths
    assert "/v1/status" in paths
    assert "/v1/ask" in paths
    assert "/v1/upload" in paths


def test_export_openapi_cli_custom_path(tmp_path: Path) -> None:
    """CLI properly accepts custom output path via --output argument."""
    custom_target = tmp_path / "nested" / "custom_api.json"
    exit_code = main(["--output", str(custom_target)])

    assert exit_code == 0
    assert custom_target.exists()

    content = json.loads(custom_target.read_text(encoding="utf-8"))
    paths = content.get("paths", {})
    assert "/v1/ping" in paths
    assert "/v1/status" in paths
    assert "/v1/ask" in paths
    assert "/v1/upload" in paths


def test_export_openapi_cli_short_flag(tmp_path: Path) -> None:
    """CLI properly accepts custom output path via -o argument."""
    custom_target = tmp_path / "short_flag" / "openapi.json"
    exit_code = main(["-o", str(custom_target)])

    assert exit_code == 0
    assert custom_target.exists()

    content = json.loads(custom_target.read_text(encoding="utf-8"))
    assert "/v1/upload" in content.get("paths", {})


def test_export_openapi_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Script handles write errors cleanly and returns non-zero exit code."""

    def mock_write_text(*args: object, **kwargs: object) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "write_text", mock_write_text)

    exit_code = main(["--output", str(tmp_path / "fail.json")])
    assert exit_code == 1

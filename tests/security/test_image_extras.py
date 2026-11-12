"""Each image installs only its own extras, so each extra must cover what
that service imports. Found on the server on 2026-11-13: the parser image
had no tldextract (the Intake Gateway imports techradar.security.urls) and
the worker image had no python-telegram-bot (worker tasks import the outbox).
Neither image could start; unit tests never saw it because the dev
environment installs every extra.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def extras() -> dict[str, list[str]]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]


def names(extra: str) -> set[str]:
    out = set()
    for dep in extras()[extra]:
        out.add(dep.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower())
    return out


def test_parser_extra_has_what_the_gateway_imports():
    assert "tldextract" in names("parser")


def test_worker_extra_has_what_the_outbox_imports():
    assert "python-telegram-bot" in names("worker")

"""The intake doors load in the bot image, which has only python-telegram-bot on top of the core
packages: no numpy, tldextract, jinja2, litellm or trafilatura (Phase 3 Task 3, Phase 6 Task 1).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

NOT_IN_BOT_IMAGE = ("numpy", "tldextract", "jinja2", "litellm", "trafilatura", "httpx_sse")
SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.parametrize(
    "module",
    [
        "techradar.bot.intake",
        "techradar.bot.voice_intake",
        "techradar.bot.routing",
        "techradar.voice.intake",
        "techradar.intake.owner_files",
    ],
)
def test_intake_modules_import_without_worker_packages(module: str) -> None:
    code = (
        "import sys\n"
        f"for name in {NOT_IN_BOT_IMAGE!r}:\n"
        "    sys.modules[name] = None  # importing it raises ImportError\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        f"import {module}\n"
    )
    res = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert res.returncode == 0, res.stderr[-800:]

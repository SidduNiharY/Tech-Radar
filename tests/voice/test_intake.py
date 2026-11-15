from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from techradar.voice.intake import (
    check_voice_bytes,
    check_voice_limits,
    intake_voice,
)


def test_voice_too_long_refused() -> None:
    assert check_voice_limits(301, 1000) == "Please keep voice notes under 5 minutes."
    assert check_voice_limits(60, 10_000_001) == "That file is too large."
    assert check_voice_limits(60, 1000) is None


def test_non_ogg_voice_refused() -> None:
    assert check_voice_bytes(b"MZ\x90\x00 fake exe") == "I can only analyse Telegram voice notes."
    assert check_voice_bytes(b"OggS\x00\x02 fake") is None


class FakeDefer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, task_name: str, **kwargs: Any) -> None:
        self.calls.append((task_name, kwargs))


@pytest.fixture
def fake_defer() -> FakeDefer:
    return FakeDefer()


@pytest.mark.db
async def test_intake_saves_private_file_and_defers(
    session: Any, tmp_path: Path, fake_defer: FakeDefer
) -> None:
    sid = await intake_voice(
        session, b"OggS fake voice audio content", 60, tmp_path, defer=fake_defer
    )
    f = next((tmp_path / "in").iterdir())
    assert f.stat().st_mode & 0o777 == 0o640
    assert fake_defer.calls[0][0] == "analyse_voice"
    assert sid > 0

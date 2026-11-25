"""Voice note intake (Phase 6 Task 1), with attack tests.

SEC: SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from techradar.intake.media import MediaInfo, MediaProbeError
from techradar.intake.owner_files import UnsafeFile
from techradar.voice import intake as voice_intake
from techradar.voice.intake import (
    NOT_VOICE_REPLY,
    VoiceRefused,
    check_voice_bytes,
    check_voice_limits,
    claim_voice_notice,
    intake_voice,
    voice_file_problem,
)

OGG = b"OggS\x00\x02" + b"v" * 200


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_voice_too_long_refused() -> None:
    assert check_voice_limits(301, 1000) == "Please keep voice notes under 5 minutes."
    assert check_voice_limits(60, 10_000_001) == "That file is too large."
    assert check_voice_limits(60, 1000) is None
    assert check_voice_limits(60, -1) == "That file is too large."


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


def _session() -> MagicMock:
    from unittest.mock import AsyncMock

    session = MagicMock()
    added: list[Any] = []
    session.add.side_effect = added.append

    async def flush() -> None:
        for row in added:
            row.id = 9

    session.flush = AsyncMock(side_effect=flush)
    session.commit = AsyncMock()
    session.added = added
    return session


@pytest.mark.parametrize(
    ("data", "duration", "reply"),
    [
        (b"MZ\x90\x00" + b"x" * 100, 60, NOT_VOICE_REPLY),
        (b"ID3\x04 an mp3", 60, NOT_VOICE_REPLY),
        (b"OggS" + b"x" * 10_000_000, 60, "That file is too large."),
        (OGG, 301, "Please keep voice notes under 5 minutes."),
    ],
)
async def test_intake_refuses_bad_bytes_before_saving(
    tmp_path: Path, fake_defer: FakeDefer, data: bytes, duration: int, reply: str
) -> None:
    session = _session()
    with pytest.raises(VoiceRefused) as exc:
        await intake_voice(session, data, duration, tmp_path, defer=fake_defer)
    assert exc.value.reply == reply
    assert not (tmp_path / "in").exists() and fake_defer.calls == [] and session.added == []


async def test_intake_names_the_file_by_hash_commits_then_defers(
    tmp_path: Path, fake_defer: FakeDefer
) -> None:
    session = _session()
    now = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
    sid = await intake_voice(session, OGG, 60, tmp_path, defer=fake_defer, now=now)
    name = hashlib.sha256(OGG).hexdigest() + ".ogg"
    assert _names(tmp_path / "in") == [name]
    assert (tmp_path / "in" / name).stat().st_mode & 0o777 == 0o640
    (row,) = session.added
    assert row.audio_path == str(tmp_path / "in" / name)
    assert row.delete_after == now + timedelta(hours=24)  # deleted even if never analysed
    session.commit.assert_awaited_once()  # the job finds its row
    assert fake_defer.calls == [("analyse_voice", {"session_id": 9})] and sid == 9


async def test_intake_never_follows_a_symlink_planted_in_the_voice_folder(
    tmp_path: Path, fake_defer: FakeDefer
) -> None:
    victim = tmp_path / "victim"
    victim.write_text("keep")
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    (voice_dir / "in" / (hashlib.sha256(OGG).hexdigest() + ".ogg")).symlink_to(victim)
    session = _session()
    with pytest.raises(UnsafeFile):
        await intake_voice(session, OGG, 60, voice_dir, defer=fake_defer)
    assert victim.read_text() == "keep" and fake_defer.calls == [] and session.added == []


async def test_intake_refuses_a_voice_folder_that_is_a_symlink(
    tmp_path: Path, fake_defer: FakeDefer
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "in").symlink_to(elsewhere)
    with pytest.raises(UnsafeFile):
        await intake_voice(_session(), OGG, 60, tmp_path / "voice", defer=fake_defer)
    assert _names(elsewhere) == []


# --- the analysis-time check ----------------------------------------------------------------


def _info(fmt: str = "ogg", audio: bool = True, video: bool = False, dur: float = 60.0):
    return MediaInfo(format_name=fmt, duration_s=dur, has_audio=audio, has_video=video)


def test_voice_file_problem_accepts_a_real_ogg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[Path, str]] = []

    def probe(path: Path, demuxer: str) -> MediaInfo:
        seen.append((path, demuxer))
        return _info()

    monkeypatch.setattr(voice_intake, "probe_media", probe)
    f = tmp_path / "a.ogg"
    f.write_bytes(OGG)
    assert voice_file_problem(f) is None
    assert seen == [(f, "ogg")]  # the ogg demuxer only, never auto-detected


@pytest.mark.parametrize(
    ("info", "problem"),
    [
        (_info(fmt="mp3"), "container 'mp3'"),
        (_info(fmt="matroska,webm"), "container 'matroska,webm'"),
        (_info(audio=False), "container 'ogg'"),
        (_info(video=True), "container 'ogg'"),
        (_info(dur=400.0), "too long"),
    ],
)
def test_voice_file_problem_refuses_what_ffprobe_does_not_call_a_voice_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, info: MediaInfo, problem: str
) -> None:
    monkeypatch.setattr(voice_intake, "probe_media", lambda p, d: info)
    f = tmp_path / "a.ogg"
    f.write_bytes(OGG)
    assert voice_file_problem(f) == problem


def test_voice_file_problem_refuses_when_ffprobe_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def probe(path: Path, demuxer: str) -> MediaInfo:
        raise MediaProbeError("ffprobe refused the file: bad")

    monkeypatch.setattr(voice_intake, "probe_media", probe)
    f = tmp_path / "a.ogg"
    f.write_bytes(OGG)
    assert voice_file_problem(f) == "ffprobe refused the file: bad"


def test_voice_file_problem_refuses_links_big_files_and_other_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice_intake, "probe_media", lambda p, d: _info())
    target = tmp_path / "target.ogg"
    target.write_bytes(OGG)
    link = tmp_path / "link.ogg"
    link.symlink_to(target)
    assert voice_file_problem(link) == "not a regular file"
    assert voice_file_problem(tmp_path) == "not a regular file"
    assert voice_file_problem(tmp_path / "missing.ogg") == "missing"
    big = tmp_path / "big.ogg"
    big.write_bytes(b"OggS" + b"x" * 10_000_000)
    assert voice_file_problem(big) == "too large"
    exe = tmp_path / "exe.ogg"
    exe.write_bytes(b"MZ\x90\x00" + b"x" * 100)
    assert voice_file_problem(exe) == "not ogg"


# --- database (run on the server) ------------------------------------------------------------


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


@pytest.mark.db
async def test_privacy_notice_is_claimed_once_per_chat(session: Any) -> None:
    chat_id = -987_654_321  # a fake chat; never the owner's
    assert await claim_voice_notice(session, chat_id) is True
    assert await claim_voice_notice(session, chat_id) is False

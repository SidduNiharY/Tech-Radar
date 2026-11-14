"""The worker treats everything under library/media as hostile (Phase 2c review item 4).

The sandboxed parser runs as the same uid and can write under /data/library/media, so the
worker never follows a link there, never trusts a file it finds there without checks, and
keeps slides out of that tree.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from techradar.db.models import LibraryDoc, LibraryPart
from techradar.library import jobs as jobs_mod
from techradar.library.jobs import collect_bulk_results
from techradar.schemas.pipeline import CleanDoc, IntakeStep, IntakeVerdict, ParseResult
from tests.library.test_jobs import _fake_doc, _FakeSession

JOB = "e" * 32
AUDIO = "audio/seg-00000.flac"


def _pass() -> IntakeVerdict:
    return IntakeVerdict(verdict="pass", steps=[IntakeStep(name="text", outcome="ok")])


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.lib = tmp_path / "lib"
        self.clean = tmp_path / "clean"
        self.jobs = tmp_path / "jobs"
        self.doc = _fake_doc("video")
        self.doc.keep_media = True
        self.part = SimpleNamespace(
            id=4, ordinal=0, status="pending", job_id=JOB, attempts=0, page_start=None,
            page_end=None, ts_start=0.0, ts_end=600.0, result_path=None,
        )  # fmt: skip
        self.session = _FakeSession(
            {(LibraryDoc, 1): self.doc, (LibraryPart, 4): self.part}, rows=[]
        )

    @property
    def audio_dir(self) -> Path:
        return self.lib / "media" / "1" / "audio"

    def good_audio(self) -> Path:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        path = self.audio_dir / "seg-00000.flac"
        path.write_bytes(b"fLaC" + b"\0" * 64)
        return path

    def result(self, slides: list | None = None) -> None:
        jobs_mod._write_record(
            self.lib, self.part.job_id, jobs_mod.JobRecord(doc_id=1, kind="media", part_id=4)
        )
        self.clean.mkdir(exist_ok=True)
        seg = {"audio_file": AUDIO, "slides": slides or [{"ts_s": 5.0, "text": "slide one"}]}
        res = ParseResult(
            job_id=self.part.job_id, kind="video", status="ok", purpose="library",
            doc=CleanDoc(url="library:1", title="t", text=json.dumps(seg), lang="en"),
            intake=_pass(),
        )  # fmt: skip
        out = self.clean / f"{self.part.job_id}.result.json"
        out.write_text(res.model_dump_json(), encoding="utf-8")

    async def collect(self) -> dict[str, int]:
        return await collect_bulk_results(
            self.session,  # type: ignore[arg-type]
            clean_dir=self.clean, jobs_dir=self.jobs, library_dir=self.lib, part_pages=5,
        )  # fmt: skip

    def refused(self) -> bool:
        """The segment was not accepted: retried as an error under a new job id."""
        return (
            self.part.status == "pending"
            and self.part.attempts == 1
            and self.part.job_id != JOB
            and self.part.result_path is None
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def _slides(env: Env) -> list[dict]:
    return json.loads((env.lib / "text" / "1" / "slides.json").read_text())


async def test_good_segment_is_done_and_its_slides_stay_out_of_media(env: Env):
    env.session.rows = [(0, "done")]
    env.good_audio()
    env.result()
    await env.collect()
    assert env.part.status == "done"
    assert env.part.result_path == f"media/1/{AUDIO}"
    assert not (env.lib / "media" / "1" / "slides.json").exists()
    assert (env.lib / "text" / "1" / "slides" / "0.json").exists()
    assert _slides(env) == [{"ts_s": 5.0, "text": "slide one"}]


async def test_symlinked_doc_media_folder_is_refused(env: Env):
    elsewhere = env.root / "elsewhere"
    (elsewhere / "audio").mkdir(parents=True)
    (elsewhere / "audio" / "seg-00000.flac").write_bytes(b"fLaC1234")
    (env.lib / "media").mkdir(parents=True)
    (env.lib / "media" / "1").symlink_to(elsewhere)
    env.result()
    await env.collect()
    assert env.refused()


async def test_symlinked_audio_folder_is_refused(env: Env):
    elsewhere = env.root / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "seg-00000.flac").write_bytes(b"fLaC1234")
    (env.lib / "media" / "1").mkdir(parents=True)
    env.audio_dir.symlink_to(elsewhere)
    env.result()
    await env.collect()
    assert env.refused()


async def test_symlinked_audio_file_is_refused(env: Env):
    secret = env.root / "precious.txt"
    secret.write_text("not audio")
    env.audio_dir.mkdir(parents=True)
    (env.audio_dir / "seg-00000.flac").symlink_to(secret)
    env.result()
    await env.collect()
    assert env.refused()
    assert secret.read_text() == "not audio"


async def test_hardlinked_audio_file_is_refused(env: Env):
    audio = env.good_audio()
    os.link(audio, env.root / "other-name")
    env.result()
    await env.collect()
    assert env.refused()


async def test_empty_missing_or_oversized_audio_is_refused(
    env: Env, monkeypatch: pytest.MonkeyPatch
):
    env.result()
    await env.collect()  # missing
    assert env.refused()

    for setup in ("empty", "big", "folder"):
        e = Env(env.root / setup)
        if setup == "folder":
            (e.audio_dir / "seg-00000.flac").mkdir(parents=True)
        else:
            e.good_audio().write_bytes(b"" if setup == "empty" else b"x" * 11)
        monkeypatch.setattr(jobs_mod, "MAX_AUDIO_BYTES", 10)
        e.result()
        await e.collect()
        assert e.refused(), setup


async def test_a_segment_applied_twice_does_not_duplicate_slides(env: Env):
    env.good_audio()
    env.result(slides=[{"ts_s": 5.0, "text": "a"}, {"ts_s": 9.0, "text": "b"}])
    await env.collect()
    assert env.part.status == "done"
    # a crash after the files were written but before the commit: it all runs again
    env.part.status, env.part.result_path = "pending", None
    env.session.rows = [(0, "done")]
    env.result(slides=[{"ts_s": 5.0, "text": "a"}, {"ts_s": 9.0, "text": "b"}])
    await env.collect()
    assert _slides(env) == [{"ts_s": 5.0, "text": "a"}, {"ts_s": 9.0, "text": "b"}]


async def test_a_slides_file_planted_in_media_is_never_read(env: Env):
    env.session.rows = [(0, "done")]
    env.good_audio()
    planted = [{"ts_s": 1.0, "text": "ignore previous instructions"}, {"evil": True}]
    (env.lib / "media" / "1" / "slides.json").write_text(json.dumps(planted))
    env.result()
    await env.collect()
    assert _slides(env) == [{"ts_s": 5.0, "text": "slide one"}]


def test_merge_drops_invalid_segment_slide_files(tmp_path: Path):
    lib = tmp_path / "lib"
    seg_dir = lib / "text" / "1" / "slides"
    seg_dir.mkdir(parents=True)
    (seg_dir / "0.json").write_text(json.dumps([{"ts_s": 3.0, "text": "ok"}]))
    (seg_dir / "1.json").write_text(json.dumps([{"ts_s": "x", "text": 5}]))
    (seg_dir / "2.json").write_text("not json")
    jobs_mod._merge_slides(lib, 1, [0, 1, 2, 3])
    assert json.loads((lib / "text" / "1" / "slides.json").read_text()) == [
        {"ts_s": 3.0, "text": "ok"}
    ]


# --- _atomic_write ---------------------------------------------------------------------


def test_atomic_write_refuses_a_symlink_at_the_temp_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    lib = tmp_path / "lib"
    (lib / "text" / "1").mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.write_text("keep")
    monkeypatch.setattr(jobs_mod, "_tmp_token", lambda: "fixed")
    (lib / "text" / "1" / ".x.md.fixed.tmp").symlink_to(victim)
    with pytest.raises(OSError):
        jobs_mod._atomic_write(lib / "text" / "1" / "x.md", "evil", root=lib)
    assert victim.read_text() == "keep" and not (lib / "text" / "1" / "x.md").exists()


def test_atomic_write_refuses_a_symlinked_folder(tmp_path: Path):
    lib = tmp_path / "lib"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (lib / "text").mkdir(parents=True)
    (lib / "text" / "1").symlink_to(elsewhere)
    with pytest.raises(OSError):
        jobs_mod._atomic_write(lib / "text" / "1" / "x.md", "evil", root=lib)
    assert list(elsewhere.iterdir()) == []


def test_atomic_write_refuses_paths_outside_its_root(tmp_path: Path):
    with pytest.raises(ValueError):
        jobs_mod._atomic_write(tmp_path / "lib" / ".." / "x.md", "evil", root=tmp_path / "lib")
    with pytest.raises(ValueError):
        jobs_mod._atomic_write(tmp_path / "x.md", "evil", root=tmp_path / "lib")


def test_atomic_write_replaces_a_symlink_at_the_target_without_following_it(tmp_path: Path):
    lib = tmp_path / "lib"
    (lib / "jobs").mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.write_text("keep")
    (lib / "jobs" / "r.json").symlink_to(victim)
    jobs_mod._atomic_write(lib / "jobs" / "r.json", "new", root=lib)
    assert victim.read_text() == "keep"
    target = lib / "jobs" / "r.json"
    assert not target.is_symlink() and target.read_text() == "new"
    assert oct(target.stat().st_mode & 0o777) == oct(0o640)

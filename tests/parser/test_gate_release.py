"""build_gate: owner_released comes only from the validated ParseJob; linked originals refused."""

from __future__ import annotations

from pathlib import Path

import pytest

import techradar.parser.main as main_mod
from techradar.intake.av import AvResult
from techradar.parser.main import build_gate
from techradar.schemas.pipeline import ParseJob, ParseResult

HAS_FIELD = "owner_released" in ParseJob.model_fields


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        raise AssertionError("never scanned")


def _job(**kw) -> ParseJob:
    fields = {
        "job_id": "a" * 32,
        "kind": "pdf",
        "raw_name": "b" * 64 + ".pdf",
        "url": "library:1",
        "source_id": 0,
        "origin": "library",
        "purpose": "library",
        "mode": "probe",
        "doc_id": 1,
    }
    fields.update(kw)
    return ParseJob(**fields)


@pytest.fixture
def captured(tmp_path, monkeypatch):
    seen: dict = {}

    def fake_gate_job(job, raw_dir, quarantine_dir, **kw):
        seen["raw_dir"] = raw_dir
        seen["owner_released"] = kw.get("owner_released")
        return ParseResult(job_id=job.job_id, kind=job.kind, status="empty")

    monkeypatch.setattr(main_mod, "gate_job", fake_gate_job)
    library = tmp_path / "library"
    (library / "originals").mkdir(parents=True)
    (library / "originals" / ("b" * 64 + ".pdf")).write_bytes(b"%PDF-1.4\n")
    gate = build_gate(
        tmp_path / "raw",
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits={},
        library_dir=library,
    )
    return gate, seen, library


def test_not_released_by_default(captured, monkeypatch):
    gate, seen, library = captured
    monkeypatch.setenv("TR_OWNER_RELEASED", "1")  # the environment can never release
    gate(_job())
    assert seen["owner_released"] is False
    assert seen["raw_dir"] == library / "originals"


@pytest.mark.skipif(not HAS_FIELD, reason="ParseJob.owner_released not in the schema yet")
def test_release_comes_from_the_validated_job(captured):
    gate, seen, library = captured
    gate(_job(owner_released=True))
    assert seen["owner_released"] is True
    # The released re-run reads the file from the originals folder like any library job.
    assert seen["raw_dir"] == library / "originals"


@pytest.mark.skipif(HAS_FIELD, reason="the schema has the field now")
def test_a_job_file_cannot_smuggle_a_release_before_the_field_exists():
    with pytest.raises(ValueError):
        ParseJob.model_validate_json(_job().model_dump_json()[:-1] + ', "owner_released": true}')


def test_symlinked_original_is_rejected_before_any_check(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(main_mod, "gate_job", lambda *a, **k: called.append(1))
    library = tmp_path / "library"
    (library / "originals").mkdir(parents=True)
    target = tmp_path / "secret.pdf"
    target.write_bytes(b"%PDF-1.4\n")
    (library / "originals" / ("b" * 64 + ".pdf")).symlink_to(target)
    gate = build_gate(
        tmp_path / "raw",
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits={},
        library_dir=library,
    )
    res = gate(_job())
    assert res.status == "rejected" and not called
    assert res.intake is not None and res.intake.verdict == "reject"

from datetime import date
from pathlib import Path

import yaml

from techradar.intake.av import AvResult
from techradar.intake.gateway import combine, gate_job
from techradar.parser.limits import parse_job
from techradar.parser.main import build_gate, serve_once
from techradar.schemas.pipeline import IntakeStep, ParseJob

FIX_DIR = Path(__file__).parent / "fixtures"
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 8)


class FakeAvScanner:
    def __init__(self, result: AvResult | None = None) -> None:
        self.result = result or AvResult(status="clean", db_date=TODAY)

    def scan(self, path: Path) -> AvResult:
        return self.result


def test_combine_worst_wins():
    step1 = IntakeStep(name="source", outcome="ok", detail="")
    step2 = IntakeStep(name="links", outcome="flag", detail="")
    step3 = IntakeStep(name="structure", outcome="quarantine", detail="")
    assert combine([step1, step2, step3]) == "quarantine"

    step4 = IntakeStep(name="type", outcome="reject", detail="")
    assert combine([step1, step2, step3, step4]) == "reject"


def test_xxe_fixture_not_resolved(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    quarantine_dir = tmp_path / "quarantine"
    quarantine_dir.mkdir()

    raw_file = raw_dir / ("a" * 64 + ".xml")
    raw_file.write_bytes((FIX_DIR / "feed_xxe.xml").read_bytes())

    job = ParseJob(
        job_id="1" * 32,
        kind="feed",
        raw_name=raw_file.name,
        url="https://pib.gov.in/feed.xml",
        source_id=1,
    )

    res = gate_job(
        job,
        raw_dir,
        quarantine_dir,
        av=FakeAvScanner(),
        allowed_hosts=frozenset({"pib.gov.in"}),
        limits=LIMITS,
        parse=lambda j: parse_job(j, raw_dir),
        today=TODAY,
    )

    assert res.status == "rejected"
    assert "root:" not in res.model_dump_json()


def test_gate_job_quarantines_and_copies_file(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    quarantine_dir = tmp_path / "quarantine"
    quarantine_dir.mkdir()

    raw_file = raw_dir / ("b" * 64 + ".pdf")
    raw_file.write_bytes((FIX_DIR / "pdf_with_js.pdf").read_bytes())

    job = ParseJob(
        job_id="2" * 32,
        kind="pdf",
        raw_name=raw_file.name,
        url="https://pib.gov.in/doc.pdf",
        source_id=1,
    )

    res = gate_job(
        job,
        raw_dir,
        quarantine_dir,
        av=FakeAvScanner(),
        allowed_hosts=frozenset({"pib.gov.in"}),
        limits=LIMITS,
        parse=lambda j: parse_job(j, raw_dir),
        today=TODAY,
    )

    assert res.status == "quarantined"
    isolated = quarantine_dir / job.job_id / raw_file.name
    assert isolated.exists()
    assert oct(isolated.stat().st_mode & 0o777) == oct(0o400)


def test_intake_wait_leaves_job_file(tmp_path: Path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    raw_dir = tmp_path / "raw"
    clean_dir = tmp_path / "clean"
    jobs_dir.mkdir()
    raw_dir.mkdir()
    clean_dir.mkdir()

    raw_file = raw_dir / ("c" * 64 + ".html")
    raw_file.write_bytes(
        b"<html><body><article><p>" + b"Hello world " * 30 + b"</p></article></body></html>"
    )

    job = ParseJob(
        job_id="3" * 32,
        kind="page",
        raw_name=raw_file.name,
        url="https://pib.gov.in/page",
        source_id=1,
    )
    job_file = jobs_dir / f"{job.job_id}.job.json"
    job_file.write_text(job.model_dump_json())

    # clamd down: the scanner reports an error and the gateway makes the job wait
    gate = build_gate(
        raw_dir,
        tmp_path / "quarantine",
        av=FakeAvScanner(AvResult(status="error")),
        allowed_hosts=frozenset({"pib.gov.in"}),
        limits=LIMITS,
    )
    count = serve_once(jobs_dir, raw_dir, clean_dir, gate=gate)
    assert count == 0
    # Job file must not be removed when waiting
    assert job_file.exists()

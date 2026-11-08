from pathlib import Path

import pytest
import yaml

from techradar.intake.filetype import (
    check_size,
    check_source,
    check_type,
    detect_mime,
)
from techradar.schemas.pipeline import ParseJob

FIX_DIR = Path(__file__).parent / "fixtures"
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())


def make_job(
    kind: str = "page",
    url: str = "https://pib.gov.in/article",
    origin: str = "fetch",
) -> ParseJob:
    return ParseJob(
        job_id="a" * 32,
        kind=kind,
        raw_name="b" * 64 + (f".{kind}" if kind in ("pdf", "md") else ".html"),
        url=url,
        source_id=1,
        raw_item_id=None,
        origin=origin,
    )


@pytest.mark.parametrize("name", ["renamed_exe.pdf", "polyglot.pdf"])
def test_renamed_or_polyglot_rejected(name: str):
    data = (FIX_DIR / name).read_bytes()
    step = check_type(make_job("pdf"), detect_mime(data[:8192]), data[:1024])
    assert step.outcome == "reject"


def test_oversized_rejected():
    step = check_size(make_job("page"), 5_000_001, LIMITS)
    assert step.outcome == "reject"


def test_not_allowlisted_source_rejected():
    step = check_source(
        make_job("page", url="https://evil.example/a"),
        frozenset({"pib.gov.in"}),
    )
    assert step.outcome == "reject"


def test_allowlisted_source_ok():
    step = check_source(
        make_job("page", url="https://pib.gov.in/a"),
        frozenset({"pib.gov.in"}),
    )
    assert step.outcome == "ok"


def test_telegram_origin_source_id_zero():
    job = make_job("page", origin="telegram")
    job.source_id = 0
    assert check_source(job, frozenset()).outcome == "ok"

    job.source_id = 42
    assert check_source(job, frozenset()).outcome == "reject"

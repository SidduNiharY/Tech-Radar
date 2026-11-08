from __future__ import annotations

import hashlib
from pathlib import Path

from techradar.fetcher.store import store_raw, write_job
from techradar.schemas.pipeline import ParseJob

JOB = ParseJob(
    job_id="0123456789abcdef0123456789abcdef",
    kind="page",
    raw_name="a" * 64 + ".html",
    url="https://pib.gov.in/doc",
    source_id=1,
    origin="fetch",
)


def test_store_raw_is_content_addressed_and_private(tmp_path: Path):
    name = store_raw(b"<rss/>", tmp_path, "xml")
    assert name == hashlib.sha256(b"<rss/>").hexdigest() + ".xml"
    assert (tmp_path / name).stat().st_mode & 0o777 == 0o640


def test_store_raw_existing_returns_name(tmp_path: Path):
    name1 = store_raw(b"<html/>", tmp_path, "html")
    name2 = store_raw(b"<html/>", tmp_path, "html")
    assert name1 == name2
    assert (tmp_path / name1).exists()


def test_store_raw_pdf_ext(tmp_path: Path):
    name = store_raw(b"%PDF-1.4", tmp_path, "pdf")
    assert name.endswith(".pdf")
    assert (tmp_path / name).read_bytes() == b"%PDF-1.4"


def test_write_job_atomic(tmp_path: Path):
    p = write_job(JOB, tmp_path)
    assert ParseJob.model_validate_json(p.read_text()) == JOB
    assert not list(tmp_path.glob("*.tmp"))
    assert p.stat().st_mode & 0o777 == 0o640

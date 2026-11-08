from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple

import pytest

from techradar.parser.feed import feed_to_entries
from techradar.parser.html import html_to_doc
from techradar.parser.limits import parse_job, run_with_limits
from techradar.parser.main import serve_once
from techradar.parser.pdf import pdf_to_doc
from techradar.schemas.pipeline import JobKind, ParseJob, ParseResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def FIX(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def job_for(tmp_path: Path, fixture_name: str, kind: JobKind) -> ParseJob:
    data = FIX(fixture_name)
    ext = fixture_name.split(".")[-1]
    raw_name = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    (tmp_path / raw_name).write_bytes(data)
    job_id = hashlib.sha256(fixture_name.encode()).hexdigest()[:32]
    return ParseJob(
        job_id=job_id,
        kind=kind,
        raw_name=raw_name,
        url=f"https://pib.gov.in/{fixture_name}",
        source_id=1,
    )


def job_for_bytes(
    tmp_path: Path,
    data: bytes,
    kind: JobKind,
    ext: str = "html",
) -> ParseJob:
    raw_name = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    (tmp_path / raw_name).write_bytes(data)
    job_id = hashlib.sha256(data[:100] or b"empty").hexdigest()[:32]
    return ParseJob(
        job_id=job_id,
        kind=kind,
        raw_name=raw_name,
        url="https://pib.gov.in/test",
        source_id=1,
    )


def long_article(char_count: int) -> bytes:
    p_len = 180
    count = (char_count // p_len) + 10
    body = "\n".join(
        (
            f"<p>Section {i}: The Reserve Bank of India monetary policy committee review and "
            f"repo rate discussions continue to assess macroeconomic growth and inflation "
            f"trends across sectors in period {i} of fiscal development analysis.</p>"
        )
        for i in range(count)
    )
    html = (
        f"<!DOCTYPE html><html><head><title>Long Policy Report</title></head>"
        f"<body><article>{body}</article></body></html>"
    )
    return html.encode("utf-8")


class ParserDirs(NamedTuple):
    jobs: Path
    raw: Path
    clean: Path


@pytest.fixture
def dirs(tmp_path: Path) -> ParserDirs:
    jobs_dir = tmp_path / "jobs"
    raw_dir = tmp_path / "raw"
    clean_dir = tmp_path / "clean"
    jobs_dir.mkdir()
    raw_dir.mkdir()
    clean_dir.mkdir()

    data = FIX("article.html")
    sha = hashlib.sha256(data).hexdigest()
    raw_name = f"{sha}.html"
    (raw_dir / raw_name).write_bytes(data)
    job_id = "1" * 32
    job = ParseJob(
        job_id=job_id,
        kind="page",
        raw_name=raw_name,
        url="https://pib.gov.in/a",
        source_id=1,
    )
    (jobs_dir / f"{job_id}.job.json").write_text(job.model_dump_json())
    return ParserDirs(jobs=jobs_dir, raw=raw_dir, clean=clean_dir)


def test_html_extracts_article_text_without_script():
    doc = html_to_doc(FIX("article.html"), "https://pib.gov.in/a", 100_000)
    assert doc is not None
    assert "repo rate" in doc.text.lower()
    assert "alert(1)" not in doc.text


def test_html_short_text_is_empty(tmp_path: Path):
    result = parse_job(job_for(tmp_path, "access_denied.html", "page"), tmp_path, 100_000)
    assert result.status == "empty"


def test_html_truncates_long_text():
    doc = html_to_doc(long_article(300_000), "https://pib.gov.in/a", 100_000)
    assert doc is not None
    assert doc.truncated
    assert len(doc.text) == 100_000


def test_detect_lang_in_doc():
    doc = html_to_doc(FIX("hindi.html"), "https://pib.gov.in/h", 100_000)
    assert doc is not None
    assert doc.lang == "hi"


def test_feed_to_entries_reads_fixture():
    e = feed_to_entries(FIX("feed.xml"))
    assert [x.title for x in e] == ["Item one", "Item two"]
    assert e[0].link.startswith("https://")


def test_feed_malformed_is_empty_not_crash(tmp_path: Path):
    result = parse_job(job_for(tmp_path, "garbage.xml", "feed"), tmp_path, 100_000)
    assert result.status == "empty"


def test_raw_file_too_large(tmp_path: Path):
    result = parse_job(
        job_for_bytes(tmp_path, b"x" * 6_000_000, "page"),
        tmp_path,
        100_000,
    )
    assert result.status == "too_large"


def test_run_with_limits_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TR_PARSER_TEST_SLEEP", "5")
    result = run_with_limits(job_for(tmp_path, "article.html", "page"), tmp_path, timeout_s=1)
    assert result.status == "timeout"


def test_serve_once_writes_result_and_cleans_job(dirs: ParserDirs):
    count = serve_once(dirs.jobs, dirs.raw, dirs.clean)
    assert count == 1
    assert not list(dirs.jobs.glob("*.json"))
    assert not list(dirs.clean.glob("*.tmp"))
    result_files = list(dirs.clean.glob("*.result.json"))
    assert len(result_files) == 1
    res = ParseResult.model_validate_json(result_files[0].read_text())
    assert res.status == "ok"
    assert res.doc is not None
    assert "repo rate" in res.doc.text.lower()


def test_serve_once_writes_result_and_removes_job(dirs: ParserDirs):
    assert serve_once(dirs.jobs, dirs.raw, dirs.clean) == 1
    assert not list(dirs.jobs.glob("*.json"))
    assert not list(dirs.clean.glob("*.tmp"))
    ParseResult.model_validate_json(next(dirs.clean.glob("*.result.json")).read_text())


def test_serve_once_handles_invalid_job_file(dirs: ParserDirs):
    for f in dirs.jobs.glob("*.job.json"):
        f.unlink()
    (dirs.jobs / "bad.job.json").write_text("{not json")
    assert serve_once(dirs.jobs, dirs.raw, dirs.clean) == 1
    assert not (dirs.jobs / "bad.job.json").exists()


def test_pdf_to_doc_fixture():
    doc = pdf_to_doc(FIXTURES_DIR / "tiny.pdf", "https://example.com/tiny.pdf", 100_000)
    assert doc is not None
    assert "repo rate" in doc.text.lower()
    assert doc.lang == "en"

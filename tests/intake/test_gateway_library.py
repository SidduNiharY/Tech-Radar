"""The gateway runs the archive, Office and media checks for library kinds."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from techradar.intake.av import AvResult
from techradar.intake.gateway import gate_job
from techradar.intake.office import epub_xml_safe
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult

from .library_fixtures import (
    MP4_HEAD,
    PNG_HEAD,
    XXE_DOCUMENT,
    make_docx,
    make_epub,
    make_traversal_epub,
    make_zip_bomb,
)

LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 13)


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=TODAY)


def run_gate(tmp_path: Path, kind: str, ext: str, build) -> ParseResult:
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    name = "b" * 64 + "." + ext
    build(raw / name)
    job = ParseJob(
        job_id="a" * 32,
        kind=kind,
        raw_name=name,
        url="library:x",
        source_id=0,
        origin="library",
        purpose="library",
    )

    def parse(j: ParseJob) -> ParseResult:
        doc = CleanDoc(url="library:x", title="t", text="clean text", lang="en")
        return ParseResult(job_id=j.job_id, kind=j.kind, status="ok", doc=doc)

    return gate_job(
        job,
        raw,
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits=LIMITS,
        parse=parse,
        today=TODAY,
    )


def test_clean_docx_and_epub_pass(tmp_path):
    assert run_gate(tmp_path, "docx", "docx", make_docx).status == "ok"
    assert run_gate(tmp_path, "epub", "epub", make_epub).status == "ok"


def test_zip_bomb_docx_rejected_by_the_gateway(tmp_path):
    assert run_gate(tmp_path, "docx", "docx", make_zip_bomb).status == "rejected"


def test_traversal_epub_rejected_by_the_gateway(tmp_path):
    assert run_gate(tmp_path, "epub", "epub", make_traversal_epub).status == "rejected"


def test_macro_docx_quarantined_by_the_gateway(tmp_path):
    def build(p):
        make_docx(p, extra={"word/vbaProject.bin": b"\xd0\xcf\x11\xe0fake"})

    assert run_gate(tmp_path, "docx", "docx", build).status == "quarantined"


def test_xxe_docx_rejected_by_the_gateway(tmp_path):
    def build(p):
        make_docx(p, document=XXE_DOCUMENT)

    assert run_gate(tmp_path, "docx", "docx", build).status == "rejected"


@pytest.mark.parametrize(
    ("kind", "ext", "head"),
    [("image", "png", PNG_HEAD)],
)
def test_kinds_without_their_checks_fail_closed(tmp_path, kind, ext, head):
    # Images have no structure check in phase 2c, so they are refused.
    def build(p):
        p.write_bytes(head + b"\0" * 100)

    assert run_gate(tmp_path, kind, ext, build).status == "rejected"


def test_epub_doctype_allowed_but_entities_refused(tmp_path):
    # EPUB 2 XHTML often carries a plain DOCTYPE; entities are still refused.
    ok = make_epub(tmp_path / "ok.epub")
    assert epub_xml_safe(ok).outcome == "ok"
    import zipfile

    bad = make_epub(tmp_path / "bad.epub")
    with zipfile.ZipFile(bad, "a") as z:
        z.writestr(
            "OEBPS/x.xhtml",
            '<?xml version="1.0"?><!DOCTYPE html [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            "<html><body>&e;</body></html>",
        )
    assert epub_xml_safe(bad).outcome == "reject"


def test_fake_media_fails_the_probe_and_is_rejected(tmp_path):
    # An MP4 signature with no real container behind it: ffprobe refuses it,
    # and the long error text must not crash the verdict (reasons <= 120).
    def build(p):
        p.write_bytes(MP4_HEAD + b"\0" * 100)

    assert run_gate(tmp_path, "video", "mp4", build).status == "rejected"

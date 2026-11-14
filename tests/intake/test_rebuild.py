"""Phase 2c Task 3: pixel rebuild for flagged PDFs, and image re-encoding (D36)."""

import os
import shutil
from datetime import date
from pathlib import Path

import pypdfium2 as pdfium
import pytest
import yaml
from PIL import Image

from techradar.intake.av import AvResult
from techradar.intake.gateway import gate_job
from techradar.intake.rebuild import (
    MAX_RENDER_PX,
    pixel_rebuild,
    rebuild_pages,
    reencode_image,
    render_pages,
)
from techradar.parser.limits import parse_job
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult

FIX = Path(__file__).parent / "fixtures"
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 13)


def make_pdf(path: Path, n: int, size: tuple[float, float] = (612, 792)) -> Path:
    pdf = pdfium.PdfDocument.new()
    for _ in range(n):
        pdf.new_page(*size)
    pdf.save(str(path))
    return path


def test_render_pages_clamps_to_the_document(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", 3)
    pages = render_pages(pdf, tmp_path / "out", 2, 99)
    assert [p.name for p in pages] == ["page-0002.png", "page-0003.png"]


def test_render_caps_huge_pages(tmp_path):
    # A hostile page size must not become a gigantic bitmap in memory.
    pdf = make_pdf(tmp_path / "big.pdf", 1, size=(14_400, 14_400))  # 200 x 200 inches
    [page] = render_pages(pdf, tmp_path / "out", 1, 1)
    assert max(Image.open(page).size) <= MAX_RENDER_PX


def test_pixel_rebuild_marks_pages_and_uses_only_ocr_text(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", 2)
    text = pixel_rebuild(pdf, 1, 2, ocr=lambda p: f"TEXT FROM PIXELS {p.name}")
    assert text.startswith("<!-- page 1 -->\nTEXT FROM PIXELS page-0001.png")
    assert "<!-- page 2 -->\nTEXT FROM PIXELS page-0002.png" in text


def test_pixel_rebuild_stops_at_the_deadline_and_says_so(tmp_path):
    # Review of d18ebba: OCR of many pages must end inside the 120 s job limit, with
    # a visible note for the pages it did not read, never a silent gap or a timeout.
    import time

    pdf = make_pdf(tmp_path / "a.pdf", 4)
    calls = []

    def slow_ocr(p):
        calls.append(p.name)
        time.sleep(0.3)
        return "x"

    text, complete = rebuild_pages(pdf, 1, 4, slow_ocr, deadline=time.monotonic() + 0.45)
    assert not complete and len(calls) == 2
    assert "<!-- page 2 -->\nx" in text
    assert "<!-- pages 3-4 not read (time limit) -->" in text


def test_pixel_rebuild_renders_one_page_at_a_time(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", 3)
    seen = []

    def ocr(p):
        seen.append(sorted(x.name for x in p.parent.iterdir()))
        return "x"

    text, complete = rebuild_pages(pdf, 1, 3, ocr)
    assert complete and all(len(names) == 1 for names in seen)


def test_reencode_strips_metadata_and_fits(tmp_path):
    src = tmp_path / "in.jpg"
    img = Image.new("RGB", (4000, 3000), "white")
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # Make
    img.save(src, exif=exif.tobytes())
    out = reencode_image(src, tmp_path / "o.png")
    im = Image.open(out)
    assert max(im.size) <= 2048 and not im.info.get("exif") and out.suffix == ".png"


def test_reencode_refuses_decompression_bombs(tmp_path):
    src = tmp_path / "bomb.png"
    Image.new("1", (20_000, 20_000)).save(src)  # 400 MP, tiny on disk
    with pytest.raises(ValueError):
        reencode_image(src, tmp_path / "o.png")


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=TODAY)


def gate_flagged(tmp_path: Path, parse_pixels):
    raw = tmp_path / "raw"
    raw.mkdir()
    name = "c" * 64 + ".pdf"
    shutil.copy(FIX / "pdf_openaction.pdf", raw / name)  # structure: flag
    job = ParseJob(
        job_id="a" * 32, kind="pdf", raw_name=name, url="https://pib.gov.in/x.pdf", source_id=1
    )

    def structure_parse(j):
        doc = CleanDoc(url=j.url, title="t", text="TEXT FROM STRUCTURE", lang="en")
        return ParseResult(job_id=j.job_id, kind=j.kind, status="ok", doc=doc)

    return gate_job(
        job,
        raw,
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset({"pib.gov.in"}),
        limits=LIMITS,
        parse=structure_parse,
        parse_pixels=parse_pixels,
        today=TODAY,
    )


def test_flagged_pdf_uses_pixel_text(tmp_path):
    def pixels(j):
        doc = CleanDoc(url=j.url, title="t", text="TEXT FROM PIXELS", lang="en")
        return ParseResult(job_id=j.job_id, kind=j.kind, status="ok", doc=doc)

    res = gate_flagged(tmp_path, pixels)
    assert res.doc is not None and res.doc.text.startswith("TEXT FROM PIXELS")


def test_flagged_pdf_without_a_rebuild_is_rejected(tmp_path):
    # Never fall back to the PDF's own (attacker-controlled) text layer.
    assert gate_flagged(tmp_path, None).status == "rejected"


def test_parse_job_pixel_mode_runs_ocr_on_rendered_pages(tmp_path, monkeypatch):
    pdf = make_pdf(tmp_path / ("d" * 64 + ".pdf"), 2)
    monkeypatch.setattr(
        "techradar.parser.limits.offline_ocr", lambda artifacts: lambda p: "OCR " + p.name
    )
    job = ParseJob(
        job_id="a" * 32,
        kind="pdf",
        raw_name=pdf.name,
        url="u",
        source_id=1,
        mode="part",
        page_start=1,
        page_end=2,
    )
    res = parse_job(job, tmp_path, pixel_rebuild=True, artifacts_path=tmp_path)
    assert res.status == "ok" and res.doc is not None
    assert "OCR page-0001.png" in res.doc.text and "<!-- page 2 -->" in res.doc.text


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("TR_DOCLING_ARTIFACTS"), reason="needs the offline OCR models"
)
def test_real_ocr_reads_rendered_text(tmp_path):
    from techradar.parser.limits import offline_ocr

    ocr = offline_ocr(Path(os.environ["TR_DOCLING_ARTIFACTS"]))
    text = pixel_rebuild(FIX.parent.parent / "parser/fixtures/tiny.pdf", 1, 1, ocr=ocr)
    assert "repo" in text.lower()

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from techradar.parser.limits import parse_job
from techradar.parser.pdf import PdfProbe, pdf_part_to_doc, pdf_probe
from techradar.schemas.pipeline import ParseJob

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_pdf(n_pages: int, outline: list[tuple[str, int, int]]) -> bytes:
    """A hand-written PDF with a nested outline: entries are (title, page, level)."""
    objs: dict[int, str] = {}
    kids = " ".join(f"{3 + i} 0 R" for i in range(n_pages))
    objs[1] = "<< /Type /Catalog /Pages 2 0 R /Outlines 100 0 R >>"
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>"
    for i in range(n_pages):
        objs[3 + i] = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"
    # Flat chain of level-1 items; deeper levels hang off the previous shallower item.
    ids = [101 + i for i in range(len(outline))]
    parent_of: dict[int, int] = {}
    stack: list[tuple[int, int]] = []  # (level, id)
    children: dict[int, list[int]] = {100: []}
    for (_title, _page, level), oid in zip(outline, ids, strict=True):
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else 100
        parent_of[oid] = parent
        children.setdefault(parent, []).append(oid)
        children.setdefault(oid, [])
        stack.append((level, oid))
    for (title, page, _), oid in zip(outline, ids, strict=True):
        sibs = children[parent_of[oid]]
        pos = sibs.index(oid)
        s = f"<< /Title ({title}) /Parent {parent_of[oid]} 0 R /Dest [{2 + page} 0 R /Fit]"
        if pos > 0:
            s += f" /Prev {sibs[pos - 1]} 0 R"
        if pos < len(sibs) - 1:
            s += f" /Next {sibs[pos + 1]} 0 R"
        if children[oid]:
            kids = children[oid]
            s += f" /First {kids[0]} 0 R /Last {kids[-1]} 0 R /Count {len(kids)}"
        objs[oid] = s + " >>"
    top = children[100]
    objs[100] = (
        f"<< /Type /Outlines /First {top[0]} 0 R /Last {top[-1]} 0 R /Count {len(top)} >>"
        if top
        else "<< /Type /Outlines /Count 0 >>"
    )
    body = "%PDF-1.4\n"
    offsets: dict[int, int] = {}
    for n in sorted(objs):
        offsets[n] = len(body.encode("latin-1"))
        body += f"{n} 0 obj\n{objs[n]}\nendobj\n"
    xref_at = len(body.encode("latin-1"))
    size = max(objs) + 1
    body += f"xref\n0 {size}\n0000000000 65535 f \n"
    for n in range(1, size):
        body += f"{offsets[n]:010d} 00000 n \n" if n in offsets else "0000000000 65535 f \n"
    body += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    return body.encode("latin-1")


def test_pdf_probe_reads_outline(tmp_path: Path):
    p = tmp_path / "b.pdf"
    p.write_bytes(make_pdf(5, [("Money", 1, 1), ("Coins", 2, 2), ("Banks", 4, 1)]))
    probe = pdf_probe(p)
    assert probe.n_pages == 5
    assert [(e.title, e.page, e.level) for e in probe.outline] == [
        ("Money", 1, 1),
        ("Coins", 2, 2),
        ("Banks", 4, 1),
    ]


def test_pdf_probe_without_outline():
    probe = pdf_probe(FIXTURES_DIR / "tiny.pdf")
    assert probe.n_pages == 1
    assert probe.outline == []


def test_probe_caps_outline_and_truncates_titles(tmp_path: Path):
    p = tmp_path / "big.pdf"
    long_title = "T" * 400
    p.write_bytes(make_pdf(3, [(long_title if i == 0 else f"c{i}", 1, 1) for i in range(600)]))
    probe = pdf_probe(p)
    assert len(probe.outline) == 500
    assert len(probe.outline[0].title) == 300


def test_pdf_probe_unreadable_file_raises(tmp_path: Path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        pdf_probe(p)


def _job(tmp_path: Path, data: bytes, **kw) -> ParseJob:
    raw_name = f"{hashlib.sha256(data).hexdigest()}.pdf"
    (tmp_path / raw_name).write_bytes(data)
    return ParseJob(
        job_id="a" * 32,
        kind="pdf",
        raw_name=raw_name,
        url="https://example.com/b.pdf",
        source_id=1,
        purpose="library",
        **kw,
    )


def test_probe_mode_returns_json_in_clean_doc(tmp_path: Path):
    job = _job(tmp_path, make_pdf(5, [("Money", 1, 1), ("Banks", 4, 1)]), mode="probe")
    res = parse_job(job, tmp_path)
    assert res.status == "ok"
    assert res.doc is not None
    assert res.doc.title == "probe"
    probe = PdfProbe.model_validate_json(res.doc.text)
    assert probe.n_pages == 5
    assert [e.title for e in probe.outline] == ["Money", "Banks"]


def test_probe_mode_bad_file_is_error(tmp_path: Path):
    res = parse_job(_job(tmp_path, b"not a pdf", mode="probe"), tmp_path)
    assert res.status == "error"
    assert res.doc is None


class FakeDoc:
    def export_to_markdown(self, page_no: int | None = None) -> str:
        return f"text of page {page_no}" if page_no != 28 else ""


class FakeConverter:
    def __init__(self):
        self.calls: list = []

    def convert(self, source, *, page_range):
        self.calls.append((Path(source).name, page_range))
        return SimpleNamespace(document=FakeDoc())


def test_part_mode_writes_page_markers(tmp_path: Path):
    p = tmp_path / "b.pdf"
    p.write_bytes(make_pdf(30, []))
    conv = FakeConverter()
    doc = pdf_part_to_doc(p, "https://example.com/b.pdf", 26, 29, converter=conv)
    assert conv.calls == [("b.pdf", (26, 29))]
    assert doc is not None
    assert doc.text.splitlines()[0] == "<!-- page 26 -->"
    assert "<!-- page 27 -->\ntext of page 27" in doc.text
    assert "<!-- page 28 -->" in doc.text  # empty page keeps its marker
    assert doc.text.index("<!-- page 28 -->") < doc.text.index("<!-- page 29 -->")


def test_part_mode_via_parse_job_uses_page_range(tmp_path: Path, monkeypatch):
    seen = {}

    def fake(path, url, s, e, *args, **kw):
        seen["range"] = (s, e)
        from techradar.schemas.pipeline import CleanDoc

        return CleanDoc(url=url, title="part", text="<!-- page 1 -->\nx", lang="en")

    monkeypatch.setattr("techradar.parser.limits.pdf_part_to_doc", fake)
    job = _job(tmp_path, make_pdf(3, []), mode="part", page_start=1, page_end=2)
    res = parse_job(job, tmp_path)
    assert res.status == "ok"
    assert seen["range"] == (1, 2)


def test_part_mode_requires_valid_range(tmp_path: Path):
    res = parse_job(_job(tmp_path, make_pdf(3, []), mode="part"), tmp_path)
    assert res.status == "error"


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("TR_DOCLING_ARTIFACTS"),
    reason="needs the offline Docling models (TR_DOCLING_ARTIFACTS); runs in the parser image",
)
def test_part_mode_real_docling(tmp_path: Path):
    doc = pdf_part_to_doc(
        FIXTURES_DIR / "tiny.pdf",
        "https://example.com/t.pdf",
        1,
        1,
        artifacts_path=Path(os.environ["TR_DOCLING_ARTIFACTS"]),
    )
    assert doc is not None
    assert doc.text.startswith("<!-- page 1 -->")
    assert "repo rate" in doc.text.lower()


# --- Sandbox limits for part mode (Opus review of 31d56a0) ---


def test_part_mode_never_runs_docling_without_offline_models(tmp_path: Path):
    # Without a baked-in model folder Docling downloads models; in the
    # no-network parser that must be an error, never an attempt.
    p = tmp_path / "b.pdf"
    p.write_bytes(make_pdf(3, []))
    with pytest.raises(ValueError, match="offline models"):
        pdf_part_to_doc(p, "u", 1, 2, artifacts_path=None)
    with pytest.raises(ValueError, match="offline models"):
        pdf_part_to_doc(p, "u", 1, 2, artifacts_path=tmp_path / "missing")


def test_part_range_is_clamped_to_the_document(tmp_path: Path):
    p = tmp_path / "b.pdf"
    p.write_bytes(make_pdf(30, []))
    conv = FakeConverter()
    doc = pdf_part_to_doc(p, "u", 26, 10**9, converter=conv)
    assert conv.calls == [("b.pdf", (26, 30))]
    assert doc is not None and "<!-- page 31 -->" not in doc.text


def test_part_starting_past_the_end_is_refused(tmp_path: Path):
    p = tmp_path / "b.pdf"
    p.write_bytes(make_pdf(5, []))
    with pytest.raises(ValueError, match="past the end"):
        pdf_part_to_doc(p, "u", 6, 9, converter=FakeConverter())


def test_part_span_is_capped(tmp_path: Path):
    job = _job(tmp_path, make_pdf(3, []), mode="part", page_start=1, page_end=101)
    assert parse_job(job, tmp_path).status == "error"


class LongDoc:
    def export_to_markdown(self, page_no: int | None = None) -> str:
        return "w " * 30_000  # 60k chars per page


class LongConverter:
    def convert(self, source, *, page_range):
        return SimpleNamespace(document=LongDoc())


def test_long_pages_keep_every_page_marker(tmp_path: Path):
    # Truncating the joined text dropped later pages without a trace; each
    # page is now capped on its own, so every marker survives.
    p = tmp_path / "b.pdf"
    p.write_bytes(make_pdf(10, []))
    doc = pdf_part_to_doc(p, "u", 1, 10, max_chars=100_000, converter=LongConverter())
    assert doc is not None and doc.truncated
    assert len(doc.text) <= 100_000
    for n in range(1, 11):
        assert f"<!-- page {n} -->" in doc.text


def test_library_pdf_over_5_mb_is_parsed_with_its_own_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "techradar.parser.limits.pdf_probe",
        lambda p: PdfProbe(n_pages=1, outline=[]),
    )
    data = make_pdf(1, []) + b"\n%" + b"x" * 6_000_000
    job = _job(tmp_path, data, mode="probe")
    assert parse_job(job, tmp_path).status == "too_large"  # default 5 MB
    assert parse_job(job, tmp_path, max_bytes=300_000_000).status == "ok"


def test_probe_stops_walking_a_huge_outline(tmp_path: Path, monkeypatch):
    seen = {"n": 0}

    class Item:
        level = 0

        def get_dest(self):
            return None  # no destination: never kept, but still counted

        def get_title(self):
            return "x"

    class Pdf:
        def __len__(self):
            return 1

        def get_toc(self):
            while True:
                seen["n"] += 1
                yield Item()

    monkeypatch.setattr("techradar.parser.pdf.pdfium.PdfDocument", lambda path: Pdf())
    probe = pdf_probe(tmp_path / "any.pdf")
    assert probe.outline == [] and seen["n"] <= 5_001

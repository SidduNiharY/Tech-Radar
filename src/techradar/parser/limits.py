from __future__ import annotations

import contextlib
import multiprocessing
import os
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path

from techradar.intake.rebuild import pixel_rebuild as pixel_rebuild_text
from techradar.parser.docx import docx_to_doc
from techradar.parser.epub import epub_to_chapters
from techradar.parser.feed import feed_to_entries
from techradar.parser.html import html_to_doc
from techradar.parser.pdf import MAX_PART_PAGES, pdf_part_to_doc, pdf_probe, pdf_to_doc
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult
from techradar.security.text import detect_lang, sanitize_text

# Address-space (RLIMIT_AS) ceilings per job. Docling, PyTorch and ONNX
# reserve far more virtual address space than they use: on the TUF a part job
# needed about 16 GB to load (4 and 8 GB failed). Real memory is bounded by
# the parser container's cgroup limit (compose mem_limit 3g); this ceiling
# only stops runaway mappings. Light jobs keep the tight limit.
LIGHT_AS_BYTES = 2_500_000_000
MODEL_AS_BYTES = 24_000_000_000


def address_space_for(job: ParseJob, *, pixel_rebuild: bool = False) -> int:
    """The RLIMIT_AS for a job: model-backed modes need room to load."""
    if pixel_rebuild or job.kind == "docx" or (job.kind == "pdf" and job.mode == "part"):
        return MODEL_AS_BYTES
    return LIGHT_AS_BYTES


def parse_job(
    job: ParseJob,
    raw_dir: Path,
    max_chars: int = 100_000,
    *,
    max_bytes: int = 5_000_000,
    artifacts_path: Path | None = None,
    pixel_rebuild: bool = False,
) -> ParseResult:
    """Parse raw content according to the ParseJob specification.

    `pixel_rebuild` (flagged PDFs only): text comes from rendered pages read
    by the offline OCR models, never from the PDF's text layer.

    `max_bytes` comes from limits.yaml for the job's origin and kind (the
    gateway already enforced it); 5 MB stays the default for news.
    """
    raw_path = raw_dir / job.raw_name
    if not raw_path.exists():
        return ParseResult(job_id=job.job_id, kind=job.kind, status="error")
    if raw_path.stat().st_size > max_bytes:
        return ParseResult(job_id=job.job_id, kind=job.kind, status="too_large")

    test_sleep = os.getenv("TR_PARSER_TEST_SLEEP")
    if test_sleep:
        with contextlib.suppress(ValueError):
            s = float(test_sleep)
            if s > 0:
                time.sleep(s)

    if job.kind == "feed":
        try:
            entries = feed_to_entries(raw_path.read_bytes())
            status = "ok" if entries else "empty"
            return ParseResult(job_id=job.job_id, kind="feed", status=status, entries=entries)
        except ValueError as exc:
            if "xml_entities" in str(exc):
                return ParseResult(job_id=job.job_id, kind="feed", status="rejected")
            return ParseResult(job_id=job.job_id, kind="feed", status="error")
    if job.kind == "page":
        doc = html_to_doc(raw_path.read_bytes(), job.url, max_chars)
        status = "ok" if doc else "empty"
        return ParseResult(job_id=job.job_id, kind="page", status=status, doc=doc)
    if job.kind == "epub":
        try:
            chapters = epub_to_chapters(raw_path, max_chars)
        except ValueError:
            return ParseResult(job_id=job.job_id, kind="epub", status="error")
        if not chapters:
            return ParseResult(job_id=job.job_id, kind="epub", status="empty")
        # One doc; each chapter starts with a marker the library job splits on.
        text = "\n\n".join(
            f"<!-- chapter {i}: {c.title} -->\n{c.text}" for i, c in enumerate(chapters, 1)
        )[:max_chars]
        doc = CleanDoc(url=job.url, title=chapters[0].title, text=text, lang=detect_lang(text))
        return ParseResult(job_id=job.job_id, kind="epub", status="ok", doc=doc)
    if job.kind == "docx":
        try:
            doc = docx_to_doc(raw_path, job.url, max_chars)
        except Exception:
            return ParseResult(job_id=job.job_id, kind="docx", status="error")
        return ParseResult(job_id=job.job_id, kind="docx", status="ok" if doc else "empty", doc=doc)
    if job.kind == "pdf" and pixel_rebuild:
        return _rebuild_pdf(job, raw_path, max_chars, artifacts_path)
    if job.kind == "pdf" and job.mode == "probe":
        try:
            probe = pdf_probe(raw_path)
        except ValueError:
            return ParseResult(job_id=job.job_id, kind="pdf", status="error")
        doc = CleanDoc(url=job.url, title="probe", text=probe.model_dump_json(), lang="other")
        return ParseResult(job_id=job.job_id, kind="pdf", status="ok", doc=doc)
    if job.kind == "pdf" and job.mode == "part":
        start, end = job.page_start, job.page_end
        if (
            start is None
            or end is None
            or start < 1
            or end < start
            or end - start + 1 > MAX_PART_PAGES
        ):
            return ParseResult(job_id=job.job_id, kind="pdf", status="error")
        try:
            doc = pdf_part_to_doc(
                raw_path, job.url, start, end, max_chars, artifacts_path=artifacts_path
            )
        except Exception:
            return ParseResult(job_id=job.job_id, kind="pdf", status="error")
        status = "ok" if doc else "empty"
        return ParseResult(job_id=job.job_id, kind="pdf", status=status, doc=doc)
    if job.kind == "pdf":
        doc = pdf_to_doc(raw_path, job.url, max_chars)
        status = "ok" if doc else "empty"
        return ParseResult(job_id=job.job_id, kind="pdf", status=status, doc=doc)

    return ParseResult(job_id=job.job_id, kind=job.kind, status="unsupported")


def offline_ocr(artifacts_path: Path) -> Callable[[Path], str]:
    """RapidOCR with the baked-in ONNX models only (it never downloads)."""
    from rapidocr import RapidOCR

    models = Path(artifacts_path) / "RapidOcr"
    engine = RapidOCR(
        params={
            "Det.model_path": str(models / "PP-OCRv6_det_small.onnx"),
            "Rec.model_path": str(models / "PP-OCRv6_rec_small.onnx"),
            "Rec.rec_keys_path": str(models / "ppocrv6_dict.txt"),
            "Cls.model_path": str(models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
        }
    )

    def read(image: Path) -> str:
        result = engine(str(image))
        return "\n".join(getattr(result, "txts", None) or ())

    return read


def _rebuild_pdf(
    job: ParseJob, raw_path: Path, max_chars: int, artifacts_path: Path | None
) -> ParseResult:
    if artifacts_path is None or not Path(artifacts_path).is_dir():
        return ParseResult(job_id=job.job_id, kind="pdf", status="error")
    start = job.page_start or 1
    end = job.page_end or start + MAX_PART_PAGES - 1
    if start < 1 or end < start or end - start + 1 > MAX_PART_PAGES:
        return ParseResult(job_id=job.job_id, kind="pdf", status="error")
    try:
        text = sanitize_text(pixel_rebuild_text(raw_path, start, end, offline_ocr(artifacts_path)))
    except Exception:
        return ParseResult(job_id=job.job_id, kind="pdf", status="error")
    if not text.strip():
        return ParseResult(job_id=job.job_id, kind="pdf", status="empty")
    text = text[:max_chars]
    doc = CleanDoc(
        url=job.url, title=f"pages {start}-{end} (rebuilt)", text=text, lang=detect_lang(text)
    )
    return ParseResult(job_id=job.job_id, kind="pdf", status="ok", doc=doc)


def _worker_entrypoint(
    job_json: str,
    raw_dir_str: str,
    max_chars: int,
    mem_bytes: int,
    conn: Connection,
    max_bytes: int = 5_000_000,
    artifacts: str | None = None,
    pixel_rebuild: bool = False,
) -> None:
    """Worker entrypoint in spawned child process."""
    with contextlib.suppress(ValueError, OSError, AttributeError):
        import resource

        if hasattr(resource, "RLIMIT_AS"):
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            target = min(mem_bytes, hard) if hard != resource.RLIM_INFINITY else mem_bytes
            resource.setrlimit(resource.RLIMIT_AS, (target, hard))

    try:
        job = ParseJob.model_validate_json(job_json)
        result = parse_job(
            job,
            Path(raw_dir_str),
            max_chars=max_chars,
            max_bytes=max_bytes,
            artifacts_path=Path(artifacts) if artifacts else None,
            pixel_rebuild=pixel_rebuild,
        )
        conn.send((True, result.model_dump_json()))
    except Exception as exc:
        conn.send((False, str(exc)))
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def run_with_limits(
    job: ParseJob,
    raw_dir: Path,
    *,
    timeout_s: int = 120,
    mem_bytes: int = 2_500_000_000,
    max_chars: int = 100_000,
    max_bytes: int = 5_000_000,
    artifacts_path: Path | None = None,
    pixel_rebuild: bool = False,
) -> ParseResult:
    """Execute parse_job in a spawned child process with memory and timeout enforcement."""
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_worker_entrypoint,
        args=(
            job.model_dump_json(),
            str(raw_dir.resolve()),
            max_chars,
            mem_bytes,
            child_conn,
            max_bytes,
            str(artifacts_path) if artifacts_path else None,
            pixel_rebuild,
        ),
    )
    proc.start()
    child_conn.close()

    proc.join(timeout=float(timeout_s))

    if proc.is_alive():
        with contextlib.suppress(Exception):
            proc.terminate()
            proc.join(timeout=1.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1.0)
        parent_conn.close()
        return ParseResult(job_id=job.job_id, kind=job.kind, status="timeout")

    try:
        if parent_conn.poll():
            success, payload = parent_conn.recv()
            if success:
                return ParseResult.model_validate_json(payload)
        return ParseResult(job_id=job.job_id, kind=job.kind, status="error")
    except Exception:
        return ParseResult(job_id=job.job_id, kind=job.kind, status="error")
    finally:
        parent_conn.close()

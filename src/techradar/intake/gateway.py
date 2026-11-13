from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from techradar.intake.av import AvScanner, check_av
from techradar.intake.filetype import check_size, check_source, check_type, detect_file_mime
from techradar.intake.links import check_links, extract_links
from techradar.intake.media import media_steps
from techradar.intake.office import check_office, epub_xml_safe, office_xml_safe
from techradar.intake.pdfscan import check_pdf
from techradar.intake.rules import check_rules
from techradar.intake.textcheck import check_injection, pattern_hits
from techradar.intake.zipcheck import check_zip
from techradar.schemas.pipeline import (
    IntakeStep,
    IntakeVerdict,
    ParseJob,
    ParseResult,
    Verdict,
)


def combine(steps: Sequence[IntakeStep]) -> Verdict:
    """Combine step outcomes by highest severity: reject > quarantine > flag > pass."""
    outcomes = {s.outcome for s in steps}
    if "reject" in outcomes:
        return "reject"
    if "quarantine" in outcomes:
        return "quarantine"
    if "flag" in outcomes:
        return "flag"
    return "pass"


def quarantine_file(raw_path: Path, quarantine_dir: Path, job_id: str) -> Path:
    """Safely isolate a quarantined raw file with read-only permissions (0o400)."""
    target_dir = quarantine_dir / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / raw_path.name
    shutil.copy2(raw_path, target_path)
    os.chmod(target_path, 0o400)
    return target_path


MEDIA_KINDS = frozenset({"video", "audio"})
TEXT_KINDS = frozenset({"feed", "page", "md"})
MEDIA_SCAN_BYTES = 8 * 1024 * 1024


def _reasons(steps: Sequence[IntakeStep], outcomes: tuple[str, ...]) -> list[str]:
    """Up to 10 reasons, each cut to the verdict's 120-character limit."""
    return [s.detail[:120] for s in steps if s.outcome in outcomes and s.detail][:10]


def structure_steps(
    job: ParseJob, raw_path: Path, data: bytes, mime: str = "", max_media_s: int = 14_400
) -> list[IntakeStep]:
    """Step 4 for each kind. Later checks run only if the earlier ones passed."""
    if job.kind in MEDIA_KINDS:
        return media_steps(job.kind, raw_path, mime, data, max_media_s)
    if job.kind == "pdf":
        return [check_pdf(data)]
    if job.kind in ("docx", "epub"):
        zip_step = check_zip(raw_path)
        if zip_step.outcome != "ok":
            return [zip_step]
        if job.kind == "docx":
            return [zip_step, check_office(raw_path), office_xml_safe(raw_path)]
        return [zip_step, epub_xml_safe(raw_path)]
    if job.kind in TEXT_KINDS:
        return []  # parsed as text with their own safe parsers (phase 2)
    return [
        IntakeStep(
            name="structure", outcome="reject", detail=f"no structure check for kind {job.kind}"
        )
    ]


def gate_job(
    job: ParseJob,
    raw_dir: Path,
    quarantine_dir: Path,
    *,
    av: AvScanner,
    rules: Any = None,
    allowed_hosts: frozenset[str],
    limits: Mapping[str, Mapping[str, int]],
    parse: Callable[[ParseJob], ParseResult],
    guard_score: Callable[[str], float] | None = None,
    today: date | None = None,
    max_media_s: int = 14_400,
) -> ParseResult:
    """Run full Intake Gateway pipeline across raw verification, sandboxed parse,

    and content scan.
    """
    check_date = today or date.today()
    raw_path = raw_dir / job.raw_name

    if not raw_path.exists():
        step = IntakeStep(name="size", outcome="reject", detail="raw file missing")
        return ParseResult(
            job_id=job.job_id,
            kind=job.kind,
            status="error",
            intake=IntakeVerdict(verdict="reject", steps=[step], reasons=["raw file missing"]),
        )

    steps: list[IntakeStep] = []

    # 1. Source check
    steps.append(check_source(job, allowed_hosts))

    # 2. Size check, from the file system: an oversized file is never read.
    size = raw_path.stat().st_size
    steps.append(check_size(job, size, limits))
    if steps[-1].outcome == "reject":
        reasons = _reasons(steps, ("reject",))
        print(f"INTAKE reject {job.job_id} {reasons}")
        return ParseResult(
            job_id=job.job_id,
            kind=job.kind,
            status="rejected",
            intake=IntakeVerdict(verdict="reject", steps=steps, reasons=reasons),
        )

    # Media (up to 4 GB) is never loaded whole: the byte checks below see its
    # first MEDIA_SCAN_BYTES; ffprobe checks the container in the structure step.
    if job.kind in MEDIA_KINDS:
        with raw_path.open("rb") as fh:
            data = fh.read(MEDIA_SCAN_BYTES)
    else:
        data = raw_path.read_bytes()

    # 3. Type check
    mime = detect_file_mime(raw_path)
    steps.append(check_type(job, mime, data[:1024]))

    # 4. Structure check, per kind. A kind with no check here is refused
    # (fail closed), so a new kind can never skip this step by accident.
    steps.extend(structure_steps(job, raw_path, data, mime, max_media_s))

    # 5. Antivirus check
    av_res = av.scan(raw_path)
    steps.append(check_av(av_res, job.origin, check_date))

    # 6. YARA rules check
    steps.append(check_rules(rules, data))

    # Early stop on reject or quarantine
    early_verdict = combine(steps)
    if early_verdict in ("reject", "quarantine"):
        reasons = _reasons(steps, ("reject", "quarantine"))
        if early_verdict == "quarantine":
            quarantine_file(raw_path, quarantine_dir, job.job_id)
            print(f"INTAKE quarantine {job.job_id} {reasons}")
            return ParseResult(
                job_id=job.job_id,
                kind=job.kind,
                status="quarantined",
                intake=IntakeVerdict(verdict="quarantine", steps=steps, reasons=reasons),
            )
        else:
            print(f"INTAKE reject {job.job_id} {reasons}")
            return ParseResult(
                job_id=job.job_id,
                kind=job.kind,
                status="rejected",
                intake=IntakeVerdict(verdict="reject", steps=steps, reasons=reasons),
            )

    # 7. Rebuild / Parse step
    parsed = parse(job)
    if parsed.status != "ok":
        return parsed

    # 8. Post-parse text, injection, and links checks
    scoring_fn = guard_score or (lambda _: 0.0)

    # Text sanitization step (already verified during parsing)
    steps.append(IntakeStep(name="text", outcome="ok", detail="normalized NFKC"))

    content_to_check = ""
    if parsed.doc is not None:
        content_to_check = parsed.doc.text
    elif parsed.entries:
        content_to_check = "\n".join(f"{e.title} {e.summary}" for e in parsed.entries)

    # Injection check
    score = scoring_fn(content_to_check)
    hits = pattern_hits(content_to_check)
    steps.append(check_injection(score, hits))

    # Links check
    links = extract_links(content_to_check)
    steps.append(check_links(links, allowed_hosts))

    final_verdict = combine(steps)
    reasons = _reasons(steps, ("quarantine", "flag"))

    if final_verdict == "quarantine":
        quarantine_file(raw_path, quarantine_dir, job.job_id)
        print(f"INTAKE quarantine {job.job_id} {reasons}")
        return ParseResult(
            job_id=job.job_id,
            kind=job.kind,
            status="quarantined",
            intake=IntakeVerdict(verdict="quarantine", steps=steps, reasons=reasons),
        )

    return ParseResult(
        job_id=job.job_id,
        kind=job.kind,
        status="ok",
        doc=parsed.doc,
        entries=parsed.entries,
        intake=IntakeVerdict(verdict=final_verdict, steps=steps, reasons=reasons),
    )

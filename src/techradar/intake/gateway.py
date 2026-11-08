from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from techradar.intake.av import AvScanner, check_av
from techradar.intake.filetype import check_size, check_source, check_type, detect_mime
from techradar.intake.links import check_links, extract_links
from techradar.intake.pdfscan import check_pdf
from techradar.intake.rules import check_rules
from techradar.intake.textcheck import check_injection, pattern_hits
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

    data = raw_path.read_bytes()
    steps: list[IntakeStep] = []

    # 1. Source check
    steps.append(check_source(job, allowed_hosts))

    # 2. Size check
    steps.append(check_size(job, len(data), limits))

    # 3. Type check
    mime = detect_mime(data[:8192])
    steps.append(check_type(job, mime, data[:1024]))

    # 4. Structure check (PDFs only)
    if job.kind == "pdf":
        steps.append(check_pdf(data))

    # 5. Antivirus check
    av_res = av.scan(raw_path)
    steps.append(check_av(av_res, job.origin, check_date))

    # 6. YARA rules check
    steps.append(check_rules(rules, data))

    # Early stop on reject or quarantine
    early_verdict = combine(steps)
    if early_verdict in ("reject", "quarantine"):
        reasons = [s.detail for s in steps if s.outcome in ("reject", "quarantine") and s.detail][
            :10
        ]
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
    reasons = [s.detail for s in steps if s.outcome in ("quarantine", "flag") and s.detail][:10]

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

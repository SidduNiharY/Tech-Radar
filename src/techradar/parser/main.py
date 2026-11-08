from __future__ import annotations

import os
import time
from pathlib import Path

from techradar.intake.av import IntakeWait
from techradar.parser.limits import run_with_limits
from techradar.schemas.pipeline import ParseJob, ParseResult


def _extract_fallback_job_id(job_file: Path) -> str:
    name = job_file.name
    stem = name[:-9] if name.endswith(".job.json") else job_file.stem
    if len(stem) == 32 and all(c in "0123456789abcdefABCDEF" for c in stem):
        return stem.lower()
    return "0" * 32


def serve_once(jobs_dir: Path, raw_dir: Path, clean_dir: Path) -> int:
    """Scan jobs_dir for *.job.json files, process each with resource limits,

    write results atomically to clean_dir, and delete the original job file.
    Returns the count of processed jobs.
    """
    jobs_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    job_files = sorted(jobs_dir.glob("*.job.json"))
    processed = 0

    for job_file in job_files:
        if not job_file.is_file():
            continue

        try:
            content = job_file.read_text(encoding="utf-8")
            job = ParseJob.model_validate_json(content)
            result = run_with_limits(job, raw_dir)
        except IntakeWait:
            # When Intake Gateway requires waiting (e.g. clamd updating or down), leave job file
            continue
        except Exception:
            fallback_id = _extract_fallback_job_id(job_file)
            result = ParseResult(job_id=fallback_id, kind="page", status="error")

        target_path = clean_dir / f"{result.job_id}.result.json"
        tmp_path = clean_dir / f".{result.job_id}.{os.getpid()}_{time.time_ns()}.tmp"
        try:
            tmp_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            tmp_path.replace(target_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
        finally:
            job_file.unlink(missing_ok=True)

        processed += 1

    return processed


def serve_forever(
    jobs_dir: Path,
    raw_dir: Path,
    clean_dir: Path,
    poll_s: float = 2.0,
) -> None:
    """Continuously poll and process parser jobs."""
    while True:
        count = serve_once(jobs_dir, raw_dir, clean_dir)
        if count == 0:
            time.sleep(poll_s)


def main() -> None:
    from techradar.settings import get_settings

    settings = get_settings()
    jobs_dir = settings.data_dir / "parse-jobs"
    raw_dir = settings.data_dir / "raw"
    clean_dir = settings.data_dir / "clean"
    serve_forever(jobs_dir, raw_dir, clean_dir)


if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

import yaml

from techradar.intake.av import AvScanner, ClamdScanner, IntakeWait
from techradar.intake.gateway import gate_job
from techradar.intake.guard import TransformersGuard, run_guard_with_limits
from techradar.intake.rules import load_rules
from techradar.parser.limits import address_space_for, run_with_limits
from techradar.schemas.pipeline import ParseJob, ParseResult
from techradar.security.urls import load_allowlist

logger = logging.getLogger(__name__)

Gate = Callable[[ParseJob], ParseResult]

# Read-only data baked into the parser image (the parser has no network).
INFRA_DIR = Path(os.environ.get("TR_INFRA_DIR", "/app/infra"))
GUARD_MODEL_DIR = Path(os.environ.get("TR_GUARD_MODEL_DIR", "/opt/models/guard"))


def load_limits(path: Path) -> dict[str, dict[str, int]]:
    """Byte limits per origin and job kind (infra/intake/limits.yaml)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {origin: {kind: int(n) for kind, n in kinds.items()} for origin, kinds in data.items()}


def default_guard_score(model_dir: Path = GUARD_MODEL_DIR) -> Callable[[str], float]:
    """The injection model's score, or 0.0 (pattern checks only) until it is installed."""
    if not (model_dir / "config.json").exists():
        logger.warning(
            "Prompt-injection model not found at %s: pattern checks only until it is installed",
            model_dir,
        )
        return lambda _text: 0.0
    guard = TransformersGuard(model_dir)
    return lambda text: run_guard_with_limits(text, guard)


def docling_artifacts() -> Path | None:
    """Docling's offline model folder, baked into the parser image."""
    value = os.environ.get("TR_DOCLING_ARTIFACTS", "")
    return Path(value) if value else None


def build_gate(
    raw_dir: Path,
    quarantine_dir: Path,
    *,
    av: AvScanner,
    allowed_hosts: frozenset[str],
    limits: Mapping[str, Mapping[str, int]],
    rules: object = None,
    guard_score: Callable[[str], float] | None = None,
) -> Gate:
    """Every job goes through the Intake Gateway; parsing happens inside it."""

    def gate(job: ParseJob) -> ParseResult:
        return gate_job(
            job,
            raw_dir,
            quarantine_dir,
            av=av,
            rules=rules,
            allowed_hosts=allowed_hosts,
            limits=limits,
            parse=lambda j: run_with_limits(
                j,
                raw_dir,
                max_bytes=limits.get(j.origin, {}).get(j.kind, 5_000_000),
                artifacts_path=docling_artifacts(),
                mem_bytes=address_space_for(j),
            ),
            parse_pixels=lambda j: run_with_limits(
                j,
                raw_dir,
                max_bytes=limits.get(j.origin, {}).get(j.kind, 5_000_000),
                artifacts_path=docling_artifacts(),
                pixel_rebuild=True,
                mem_bytes=address_space_for(j, pixel_rebuild=True),
            ),
            guard_score=guard_score,
        )

    return gate


def _extract_fallback_job_id(job_file: Path) -> str:
    name = job_file.name
    stem = name[:-9] if name.endswith(".job.json") else job_file.stem
    if len(stem) == 32 and all(c in "0123456789abcdefABCDEF" for c in stem):
        return stem.lower()
    return "0" * 32


def serve_once(jobs_dir: Path, raw_dir: Path, clean_dir: Path, *, gate: Gate) -> int:
    """Run each *.job.json through the Intake Gateway, write the result atomically
    to clean_dir and delete the job file. A job waits (stays in place) while the
    gateway cannot decide, for example while clamd is down. Returns the count of
    processed jobs.
    """
    jobs_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    for job_file in sorted(jobs_dir.glob("*.job.json")):
        if not job_file.is_file():
            continue

        try:
            job = ParseJob.model_validate_json(job_file.read_text(encoding="utf-8"))
            result = gate(job)
        except IntakeWait:
            continue
        except Exception:
            result = ParseResult(
                job_id=_extract_fallback_job_id(job_file), kind="page", status="error"
            )

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
    jobs_dir: Path, raw_dir: Path, clean_dir: Path, gate: Gate, poll_s: float = 2.0
) -> None:
    """Continuously poll and process parser jobs."""
    while True:
        if serve_once(jobs_dir, raw_dir, clean_dir, gate=gate) == 0:
            time.sleep(poll_s)


def main() -> None:
    from techradar.settings import get_settings

    settings = get_settings()
    raw_dir = settings.data_dir / "raw"
    gate = build_gate(
        raw_dir,
        settings.data_dir / "quarantine",
        av=ClamdScanner(),
        allowed_hosts=load_allowlist(INFRA_DIR / "squid" / "allowlist.txt"),
        limits=load_limits(INFRA_DIR / "intake" / "limits.yaml"),
        rules=load_rules(INFRA_DIR / "intake" / "yara"),
        guard_score=default_guard_score(),
    )
    serve_forever(settings.data_dir / "parse-jobs", raw_dir, settings.data_dir / "clean", gate)


if __name__ == "__main__":
    main()

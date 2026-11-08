from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from techradar.schemas.pipeline import ParseJob


def store_raw(body: bytes, raw_dir: Path, ext: Literal["xml", "html", "pdf", "md"]) -> str:
    """Store raw downloaded bytes content-addressed with mode 0o640."""
    sha256 = hashlib.sha256(body).hexdigest()
    name = f"{sha256}.{ext}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / name
    if target.exists():
        return name

    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            with open(fd, "wb", closefd=True) as f:
                f.write(body)
        finally:
            os.chmod(target, 0o640)
    except FileExistsError:
        pass
    return name


def write_job(job: ParseJob, jobs_dir: Path) -> Path:
    """Write ParseJob atomically via temporary file with mode 0o640."""
    jobs_dir.mkdir(parents=True, exist_ok=True)
    target = jobs_dir / f"{job.job_id}.job.json"
    temp_file = jobs_dir / f"{job.job_id}.tmp"

    data = job.model_dump_json(indent=2).encode("utf-8")
    fd = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    try:
        with open(fd, "wb", closefd=True) as f:
            f.write(data)
    finally:
        os.chmod(temp_file, 0o640)

    os.replace(temp_file, target)
    return target

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np


def decode_audio(path: Path, *, sr: int = 16_000, timeout_s: int = 60) -> np.ndarray:
    """Decode audio file to single-channel 32-bit float PCM at specified sample rate."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "f32le",
        "-",
    ]
    res = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        timeout=timeout_s,
        check=True,
    )
    return np.frombuffer(res.stdout, dtype=np.float32)


def compute_peaks(wav: np.ndarray, n: int = 800) -> list[float]:
    """Compute normalized peak amplitudes over n discrete time buckets."""
    if len(wav) == 0 or n <= 0:
        return [0.0] * max(n, 0)

    # Split into n roughly equal chunks
    chunks = np.array_split(np.abs(wav), n)
    peaks: list[float] = []
    for c in chunks:
        if len(c) == 0:
            peaks.append(0.0)
        else:
            val = float(np.max(c))
            peaks.append(round(min(max(val, 0.0), 1.0), 3))
    return peaks

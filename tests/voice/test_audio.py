from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from techradar.voice.audio import compute_peaks, decode_audio


class FakeCompleted:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def test_compute_peaks_length_and_range() -> None:
    p = compute_peaks(np.sin(np.linspace(0, 100, 16_000)).astype("float32"), n=100)
    assert len(p) == 100
    assert all(0 <= v <= 1 for v in p)


def test_decode_audio_uses_list_args(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_run(args: list[str], **kwargs: Any) -> FakeCompleted:
        seen["a"] = (args, kwargs)
        return FakeCompleted(b"\x00" * 8)

    monkeypatch.setattr(subprocess, "run", fake_run)
    arr = decode_audio(Path("x.ogg"))
    args, kw = seen["a"]

    assert isinstance(args, list)
    assert "shell" not in kw
    assert kw["timeout"] == 60
    assert len(arr) == 2  # 8 bytes / 4 bytes per float32

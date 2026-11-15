from __future__ import annotations

from pathlib import Path

from scripts.check_model_files import run_checker


def test_rejects_pickle_files(tmp_path: Path) -> None:
    (tmp_path / "m.pth").write_bytes(b"x")
    assert run_checker(tmp_path) == 1


def test_allows_ct2_bin(tmp_path: Path) -> None:
    d = tmp_path / "whisper"
    d.mkdir()
    (d / "model.bin").write_bytes(b"x")
    (d / "config.json").write_text("{}")
    assert run_checker(tmp_path) == 0


def test_rejects_raw_bin_without_ct2(tmp_path: Path) -> None:
    (tmp_path / "random.bin").write_bytes(b"x")
    assert run_checker(tmp_path) == 1

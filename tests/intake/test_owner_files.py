"""Private, no-follow writes and reads of files the owner sends (Phase 3 Task 3, Phase 6 Task 1).

SEC: SEC-15, SEC-57.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from techradar.intake.owner_files import (
    UnsafeFile,
    read_private,
    remove_if_same,
    write_private,
)

PDF = b"%PDF-1.7\n" + b"x" * 100


def test_write_names_the_file_by_its_hash_and_keeps_it_private(tmp_path: Path) -> None:
    name = write_private(tmp_path / "in", PDF, "pdf")
    assert name == hashlib.sha256(PDF).hexdigest() + ".pdf"
    f = tmp_path / "in" / name
    assert f.read_bytes() == PDF
    assert f.stat().st_mode & 0o777 == 0o640
    assert [p.name for p in (tmp_path / "in").iterdir()] == [name]  # no temp file left


def test_write_same_content_twice_is_one_file(tmp_path: Path) -> None:
    assert write_private(tmp_path, PDF, "pdf") == write_private(tmp_path, PDF, "pdf")
    assert len(list(tmp_path.iterdir())) == 1


def test_write_refuses_unknown_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_private(tmp_path, PDF, "../x")  # type: ignore[arg-type]


def test_write_never_follows_a_symlink_planted_at_the_name(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    folder = tmp_path / "in"
    folder.mkdir()
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    (folder / name).symlink_to(victim)
    with pytest.raises(UnsafeFile):
        write_private(folder, PDF, "pdf")
    assert victim.read_text() == "keep me"
    assert sorted(p.name for p in folder.iterdir()) == [name]  # temp file cleaned up


def test_write_refuses_a_folder_that_is_a_symlink(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "in").symlink_to(elsewhere)
    with pytest.raises(UnsafeFile):
        write_private(tmp_path / "in", PDF, "pdf")
    assert list(elsewhere.iterdir()) == []


def test_write_refuses_a_dangling_symlink_folder(tmp_path: Path) -> None:
    (tmp_path / "in").symlink_to(tmp_path / "missing")
    with pytest.raises(UnsafeFile):
        write_private(tmp_path / "in", PDF, "pdf")
    assert not (tmp_path / "missing").exists()


def test_read_returns_the_bytes_of_a_checked_file(tmp_path: Path) -> None:
    name = write_private(tmp_path, PDF, "pdf")
    data, st = read_private(tmp_path, name, max_bytes=1000)
    assert data == PDF and st.st_size == len(PDF)


@pytest.mark.parametrize(
    "name",
    [
        "../etc/passwd",
        "/etc/passwd",
        "a" * 64 + ".exe",
        "A" * 64 + ".pdf",
        "a" * 64 + ".pdf/../x",
        "report.pdf",
        "",
    ],
)
def test_read_refuses_any_name_that_is_not_a_hash_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(UnsafeFile):
        read_private(tmp_path, name, max_bytes=1000)


def test_read_refuses_a_symlink(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_bytes(PDF)
    folder = tmp_path / "in"
    folder.mkdir()
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    (folder / name).symlink_to(secret)
    with pytest.raises(UnsafeFile):
        read_private(folder, name, max_bytes=1000)


def test_read_refuses_a_hard_link_to_another_file(tmp_path: Path) -> None:
    folder = tmp_path / "in"
    folder.mkdir()
    other = tmp_path / "other.pdf"
    other.write_bytes(PDF)
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    os.link(other, folder / name)
    with pytest.raises(UnsafeFile):
        read_private(folder, name, max_bytes=1000)


def test_read_refuses_content_that_does_not_match_its_name(tmp_path: Path) -> None:
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    (tmp_path / name).write_bytes(b"%PDF-1.7 swapped")
    with pytest.raises(UnsafeFile):
        read_private(tmp_path, name, max_bytes=1000)


def test_read_refuses_an_oversized_file(tmp_path: Path) -> None:
    name = write_private(tmp_path, PDF, "pdf")
    with pytest.raises(UnsafeFile):
        read_private(tmp_path, name, max_bytes=len(PDF) - 1)


def test_read_refuses_a_folder_that_is_a_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    name = write_private(real, PDF, "pdf")
    (tmp_path / "in").symlink_to(real)
    with pytest.raises(UnsafeFile):
        read_private(tmp_path / "in", name, max_bytes=1000)


def test_remove_if_same_removes_only_the_checked_inode(tmp_path: Path) -> None:
    name = write_private(tmp_path, PDF, "pdf")
    _data, st = read_private(tmp_path, name, max_bytes=1000)
    (tmp_path / name).unlink()
    (tmp_path / name).write_bytes(b"replaced")
    remove_if_same(tmp_path, name, st)
    assert (tmp_path / name).read_bytes() == b"replaced"
    _data, st = read_private(tmp_path, write_private(tmp_path, PDF + b"2", "pdf"), 1000)
    remove_if_same(tmp_path, hashlib.sha256(PDF + b"2").hexdigest() + ".pdf", st)
    assert not (tmp_path / (hashlib.sha256(PDF + b"2").hexdigest() + ".pdf")).exists()

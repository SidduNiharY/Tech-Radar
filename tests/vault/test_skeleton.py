"""Unit tests for vault skeleton generation."""

from pathlib import Path

from techradar.vault.skeleton import generate_skeleton


def test_generate_skeleton_creates_expected_pages(tmp_path: Path):
    made = generate_skeleton(tmp_path, Path("vault-seed"))
    assert len(list((tmp_path / "syllabus/gate_cs").glob("*.md"))) == 11
    assert len(list((tmp_path / "foundations").rglob("*.md"))) == 27
    assert (tmp_path / "CLAUDE.md").exists() and made


def test_generate_skeleton_is_idempotent(tmp_path: Path):
    generate_skeleton(tmp_path, Path("vault-seed"))
    assert generate_skeleton(tmp_path, Path("vault-seed")) == []


def test_generate_skeleton_never_overwrites(tmp_path: Path):
    generate_skeleton(tmp_path, Path("vault-seed"))
    (tmp_path / "memory.md").write_text("my edits")
    generate_skeleton(tmp_path, Path("vault-seed"))
    assert (tmp_path / "memory.md").read_text() == "my edits"

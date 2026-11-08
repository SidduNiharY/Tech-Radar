"""Tests for VaultMcpServer (SEC-24 path traversal prevention and note search)."""

from pathlib import Path

import pytest

from techradar.mcp.server import SecurityError, VaultMcpServer


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    """Create a populated temporary Obsidian vault."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Note 1: Standard note with frontmatter and body
    note1 = vault / "python_guide.md"
    note1.write_text(
        "---\ntitle: Python Programming Guide\nstatus: active\n---\n"
        "# Python Programming Guide\n\n"
        "Python is a clean, readable language used widely in data science and web backend.\n",
        encoding="utf-8",
    )

    # Note 2: Subfolder note with heading title
    skills_dir = vault / "skills"
    skills_dir.mkdir()
    note2 = skills_dir / "docker.md"
    note2.write_text(
        "# Docker Containers\n\n"
        "Docker allows containerizing applications with reproducible environments.\n",
        encoding="utf-8",
    )

    # Note 3: Note with title containing term that also appears in note1 body
    note3 = vault / "data_science.md"
    note3.write_text(
        "# Data Science Foundations\n\n"
        "Overview of statistics, linear algebra, and data workflows.\n",
        encoding="utf-8",
    )

    return vault


def test_init_verifies_vault_dir(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        VaultMcpServer(non_existent)


def test_read_note_returns_valid_text(temp_vault: Path) -> None:
    server = VaultMcpServer(temp_vault)
    content = server.read_note("python_guide.md")
    assert "Python Programming Guide" in content
    assert "data science and web backend" in content

    # Test reading note from subfolder
    docker_content = server.read_note("skills/docker.md")
    assert "Docker Containers" in docker_content

    # Missing note raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        server.read_note("non_existent_note.md")


def test_path_traversal_attempts_strictly_blocked(temp_vault: Path) -> None:
    server = VaultMcpServer(temp_vault)

    traversal_payloads = [
        "../../etc/passwd",
        "/etc/shadow",
        "/etc/passwd",
        "skills/../../etc/passwd",
        "skills/../..",
        "../vault/../etc/hosts",
    ]

    for payload in traversal_payloads:
        with pytest.raises((ValueError, SecurityError)):
            server.read_note(payload)

        with pytest.raises((ValueError, SecurityError)):
            server.list_topics(payload)


def test_symlinks_pointing_outside_vault_rejected(temp_vault: Path, tmp_path: Path) -> None:
    server = VaultMcpServer(temp_vault)

    # Create secret outside vault
    outside_file = tmp_path / "secret_creds.txt"
    outside_file.write_text("SUPER_SECRET_TOKEN=xyz123", encoding="utf-8")

    # Create symlink inside vault pointing to secret outside vault
    symlink_note = temp_vault / "leak.md"
    symlink_note.symlink_to(outside_file)

    # Reading through symlink pointing outside vault MUST raise ValueError/SecurityError
    with pytest.raises((ValueError, SecurityError)):
        server.read_note("leak.md")

    # Search should NOT leak content from symlink pointing outside
    results = server.search_notes("SUPER_SECRET_TOKEN")
    assert len(results) == 0


def test_symlinks_pointing_inside_vault_allowed(temp_vault: Path) -> None:
    server = VaultMcpServer(temp_vault)

    # Symlink pointing to an internal note is allowed
    target = temp_vault / "python_guide.md"
    symlink_internal = temp_vault / "skills" / "python_alias.md"
    symlink_internal.symlink_to(target)

    content = server.read_note("skills/python_alias.md")
    assert "Python Programming Guide" in content


def test_search_notes_returns_matching_files(temp_vault: Path) -> None:
    server = VaultMcpServer(temp_vault)

    results = server.search_notes("Docker")
    assert len(results) == 1
    assert results[0]["path"] == "skills/docker.md"
    assert results[0]["title"] == "Docker Containers"
    assert "containerizing" in results[0]["snippet"].lower()

    # Search in frontmatter/body
    results_py = server.search_notes("backend")
    assert len(results_py) >= 1
    assert any(r["path"] == "python_guide.md" for r in results_py)

    # Search non-matching query
    results_empty = server.search_notes("nonexistent_keyword_xyz")
    assert results_empty == []


def test_search_notes_ranks_title_matches_first(temp_vault: Path) -> None:
    server = VaultMcpServer(temp_vault)

    # Query 'Data Science':
    # - note 'data_science.md' has 'Data Science Foundations' in title -> rank first
    # - note 'python_guide.md' mentions 'data science' in body text -> rank lower
    results = server.search_notes("Data Science")
    assert len(results) >= 2
    assert results[0]["title"] == "Data Science Foundations"
    assert results[0]["path"] == "data_science.md"
    assert results[1]["path"] == "python_guide.md"


def test_list_topics_safely(temp_vault: Path) -> None:
    server = VaultMcpServer(temp_vault)

    top_topics = server.list_topics()
    assert "skills" in top_topics
    assert "python_guide.md" in top_topics

    skills_topics = server.list_topics("skills")
    assert "docker.md" in skills_topics

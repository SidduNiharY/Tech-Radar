"""Unit tests for duplicate clustering and relevance filter."""

from pathlib import Path

import pytest

from techradar.pipeline.filter import assign_cluster, cosine, profile_texts, relevance


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    context_dir = vault / "context"
    context_dir.mkdir()
    (context_dir / "interests.md").write_text(
        "# Interests\n\nBanking awareness\nFull-stack AI developer\n"
    )
    syllabus_dir = vault / "syllabus" / "gate_cs"
    syllabus_dir.mkdir(parents=True)
    (syllabus_dir / "os.md").write_text("---\ntitle: Operating System\n---\nBody")
    return vault


def test_cosine_basics():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([0, 0], [1, 0]) == 0.0


def test_assign_cluster_picks_best_above_threshold():
    assert assign_cluster([1, 0], [(7, [0.95, 0.31]), (9, [1, 0.01])]) == 9


def test_assign_cluster_none_below_threshold():
    assert assign_cluster([1, 0], [(7, [0.5, 0.86])]) is None


def test_relevance_is_max_cosine():
    assert relevance([1, 0], [[0, 1], [1, 0]]) == pytest.approx(1.0)
    assert relevance([1, 0], []) == 0.0


def test_profile_texts_reads_interests_and_syllabus(tmp_vault):
    texts = profile_texts(tmp_vault)
    assert "Banking awareness" in texts
    assert "Operating System" in texts

"""The exam tables' value checks exist in the models and in migration 0010 alike."""

from __future__ import annotations

from pathlib import Path

import pytest

from techradar.db.models import PyqQuestion, TopicSource

MIGRATION = Path("src/techradar/db/migrations/versions/0010_exams.py")


@pytest.mark.parametrize(
    ("model", "names"),
    [
        (PyqQuestion, {"ck_pyq_questions_qtype", "ck_pyq_questions_tag_status"}),
        (TopicSource, {"ck_topic_sources_kind", "ck_topic_sources_status"}),
    ],
)
def test_value_checks_in_model_and_migration(model: type, names: set[str]):
    declared = {c.name for c in model.__table__.constraints}  # type: ignore[attr-defined]
    text = MIGRATION.read_text(encoding="utf-8")
    assert names <= declared
    assert all(n in text for n in names)

"""Unit and integration tests for fact supersession."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.pipeline.supersede import (
    FactChange,
    load_labels,
    load_subjects,
    render_fact_change,
    subject_key,
    supersede_if_newer,
)

ALIASES = {"rbi.repo_rate": ["repo rate", "policy repo rate"]}
OFFICIAL = frozenset({"rbi.org.in"})


@dataclass
class FactsHolder:
    old: int
    new_official: int
    new_from_news_only: int
    older_official: int
    repeat_of_old_value: int


def test_subject_key_matches_aliases_only():
    assert (
        subject_key("Policy Repo  Rate", ALIASES) == "rbi.repo_rate"
        and subject_key("repo", ALIASES) is None
    )


def test_render_fact_change_exact():
    c = FactChange(
        subject_key="rbi.repo_rate",
        old_fact_id=1,
        new_fact_id=2,
        old_value="5.5%",
        new_value="5.25%",
    )
    assert (
        render_fact_change(c, "Repo rate") == "Repo rate changed: 5.5% → 5.25%. Old cards updated."
    )


def test_load_subjects_and_labels():
    subjects = load_subjects(Path("infra/facts/subjects.yaml"))
    labels = load_labels(Path("infra/facts/subjects.yaml"))
    assert "rbi.repo_rate" in subjects
    assert "repo rate" in subjects["rbi.repo_rate"]
    assert labels["rbi.repo_rate"] == "Repo rate"


@pytest.mark.asyncio
async def test_supersede_if_newer_mock_logic():
    # Test unit logic of supersede_if_newer with mock session
    session = AsyncMock()
    session.add = MagicMock()

    # Fact not verified -> returns None
    fact_mock = MagicMock()
    fact_mock.id = 1
    fact_mock.status = "unverified"
    fact_mock.subject_key = "rbi.repo_rate"
    fact_mock.value = "5.25%"
    fact_mock.as_of = date(2026, 12, 1)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = fact_mock
    session.execute.return_value = result_mock

    assert await supersede_if_newer(session, 1, OFFICIAL) is None

    # Fact verified, but no official source -> returns None
    fact_mock.status = "verified"
    empty_source_result = MagicMock()
    empty_source_result.scalars.return_value.first.return_value = None
    session.execute.side_effect = [result_mock, empty_source_result]
    assert await supersede_if_newer(session, 1, OFFICIAL) is None

    # Fact verified with official source, but no older facts -> returns None
    source_mock = MagicMock()
    source_result = MagicMock()
    source_result.scalars.return_value.first.return_value = source_mock
    no_older_result = MagicMock()
    no_older_result.scalars.return_value.all.return_value = []
    session.execute.side_effect = [result_mock, source_result, no_older_result]
    assert await supersede_if_newer(session, 1, OFFICIAL) is None

    # Fact verified with official source and valid older fact -> succeeds!
    older_mock = MagicMock()
    older_mock.id = 2
    older_mock.value = "5.5%"
    older_mock.status = "verified"
    older_result = MagicMock()
    older_result.scalars.return_value.all.return_value = [older_mock]
    session.execute.side_effect = [result_mock, source_result, older_result]

    change = await supersede_if_newer(session, 1, OFFICIAL)
    assert change is not None
    assert change.old_value == "5.5%"
    assert change.new_value == "5.25%"
    assert older_mock.status == "superseded"
    assert older_mock.superseded_by == 1


@pytest.mark.db
async def test_official_newer_fact_supersedes(session, facts):
    c = await supersede_if_newer(session, facts.new_official, OFFICIAL)
    assert c is not None
    assert c.old_value == "5.5%"


@pytest.mark.db
async def test_unofficial_source_never_supersedes(session, facts):
    assert await supersede_if_newer(session, facts.new_from_news_only, OFFICIAL) is None


@pytest.mark.db
async def test_older_fact_never_supersedes_newer(session, facts):
    assert await supersede_if_newer(session, facts.older_official, OFFICIAL) is None


@pytest.mark.db
async def test_same_value_no_change(session, facts):
    assert await supersede_if_newer(session, facts.repeat_of_old_value, OFFICIAL) is None

"""Tests for user portrait generation and know-yourself grounding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from techradar.db.models import DrillAttempt, Mistake, StudySession
from techradar.night.know_yourself import generate_user_portrait, know_yourself


@dataclass
class MockRagHit:
    text: str


@dataclass
class MockRagDeps:
    hits: list[MockRagHit]


@dataclass
class DuckSession:
    study_sessions: list[StudySession]
    mistakes: list[Mistake]
    failed_drills: list[DrillAttempt]


@pytest.mark.asyncio
async def test_generate_user_portrait_with_history():
    now = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
    t1 = now - timedelta(days=2, hours=11)  # 09:00
    t2 = now - timedelta(days=1, hours=11)  # 09:00
    t3 = now - timedelta(days=1, hours=1)  # 19:00

    sessions = [
        StudySession(goal="fullstack", topic="Async IO", started_at=t1, minutes=60),
        StudySession(goal="fullstack", topic="FastAPI", started_at=t2, minutes=45),
        StudySession(goal="gate", topic="Algorithms", started_at=t3, minutes=90),
    ]
    mistakes = [
        Mistake(kind="grammar_inversion", detail="Subject auxiliary inversion", created_at=t1),
        Mistake(kind="grammar_inversion", detail="Subject auxiliary inversion", created_at=t2),
    ]
    failed_drills = [
        DrillAttempt(kind="quant_compound_interest", correct=False, at=t1, seconds=35.0),
        DrillAttempt(kind="quant_compound_interest", correct=False, at=t2, seconds=40.0),
        DrillAttempt(kind="reasoning_series", correct=False, at=t3, seconds=25.0),
    ]

    session_store = DuckSession(
        study_sessions=sessions,
        mistakes=mistakes,
        failed_drills=failed_drills,
    )

    portrait = await generate_user_portrait(session_store, days=30, now=now)

    assert "# User Learning Portrait (Past 30 Days)" in portrait
    assert "Total Study Sessions: 3" in portrait
    assert "Total Study Time: 195 minutes (3.2 hours)" in portrait
    assert "fullstack: 2 sessions (66.7%)" in portrait
    assert "gate: 1 sessions (33.3%)" in portrait
    assert "Focus Window: 09:00 - 10:00 (2 sessions)" in portrait
    assert "quant_compound_interest (2 occurrences)" in portrait
    assert "Subject auxiliary inversion (2 occurrences)" in portrait


@pytest.mark.asyncio
async def test_generate_user_portrait_empty():
    empty_store = DuckSession(study_sessions=[], mistakes=[], failed_drills=[])
    portrait = await generate_user_portrait(empty_store, days=30)

    assert "Total Study Sessions: 0" in portrait
    assert "Total Study Time: 0 minutes" in portrait
    assert "Insufficient data to determine focus windows" in portrait
    assert "None recorded" in portrait


@pytest.mark.asyncio
async def test_know_yourself_not_enough_sources(tmp_path: Path):
    deps = MockRagDeps(hits=[MockRagHit(text="Only one hit")])
    status = await know_yourself("Warangal", deps, tmp_path)
    assert status == "not_enough_sources"


@pytest.mark.asyncio
async def test_know_yourself_written(tmp_path: Path):
    deps = MockRagDeps(
        hits=[
            MockRagHit(text="Warangal was the capital of the Kakatiya dynasty."),
            MockRagHit(text="It is famous for the Thousand Pillar Temple and Warangal Fort."),
            MockRagHit(text="Major agricultural products include cotton and chili."),
        ]
    )
    status = await know_yourself("Warangal", deps, tmp_path)
    assert status == "written"

    target_file = tmp_path / "context" / "know-yourself" / "warangal.md"
    assert target_file.exists()
    content = target_file.read_text(encoding="utf-8")
    assert "Kakatiya dynasty" in content
    assert "Thousand Pillar Temple" in content

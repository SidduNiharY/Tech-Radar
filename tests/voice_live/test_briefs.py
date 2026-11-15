"""Tests for live voice briefs and question packs."""

from __future__ import annotations

import pytest

from techradar.voice_live.briefs import (
    BANK_PANEL_QUESTIONS,
    HR_QUESTIONS,
    SessionBrief,
    build_brief,
    build_live_brief,
)


def test_question_packs_count():
    assert len(HR_QUESTIONS) == 12
    assert len(BANK_PANEL_QUESTIONS) == 12
    assert "Tell me about yourself." in HR_QUESTIONS
    assert "Why banking?" in BANK_PANEL_QUESTIONS


def test_build_live_brief_bank():
    profile = {
        "name": "Siddu",
        "degree": "B.Tech Computer Science",
        "district": "Warangal",
        "state": "Telangana",
        "weak_areas": ["Banking Awareness", "Monetary Policy"],
    }
    notes = [
        "RBI kept Repo Rate unchanged at 6.5%.",
        "CPI inflation moderated to 4.8%.",
    ]
    brief = build_live_brief(profile, goal="interview_bank", context_notes=notes)

    assert "# Live Voice Session Brief: INTERVIEW_BANK" in brief
    assert "- Name: Siddu" in brief
    assert "- Degree: B.Tech Computer Science" in brief
    assert "- Location: Warangal, Telangana" in brief
    assert "RBI kept Repo Rate unchanged" in brief
    assert "Why banking?" in brief
    assert "Do not correct the user while they speak" in brief


def test_build_live_brief_tech():
    profile = {
        "name": "Alex",
        "degree": "MS Software Engineering",
        "weak_areas": ["System Design"],
    }
    notes = ["Distributed caching strategies", "Event-driven architecture"]
    brief = build_live_brief(profile, goal="interview_tech", context_notes=notes)

    assert "Alex" in brief
    assert "INTERVIEW_TECH" in brief
    assert "Technical Discussion Prompts" in brief
    assert "Do not correct the user while they speak" in brief


def test_session_brief_model():
    brief = SessionBrief(
        mode="interview_hr",
        questions=["Question 1", "Question 2"],
        facts=["Fact 1"],
        stories=["Story 1"],
        passage=None,
    )
    assert brief.mode == "interview_hr"
    assert len(brief.questions) == 2


@pytest.mark.asyncio
async def test_build_brief_helper():
    brief = await build_brief("interview_bank", None)
    assert brief.mode == "interview_bank"
    assert len(brief.questions) <= 15
    assert len(brief.facts) <= 20
    assert "Why banking?" in brief.questions[0]

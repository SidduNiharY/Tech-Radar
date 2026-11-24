from __future__ import annotations

import secrets
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from techradar.api.schemas import (
    AnswerOutcome,
    AskRequest,
    QuizQuestion,
    Ticket,
    TodayItem,
    TodayResponse,
    UserSettings,
)


def test_ask_request_validation():
    # Valid
    req = AskRequest(question="What is the current policy repo rate?")
    assert req.question == "What is the current policy repo rate?"
    assert req.verified_only is False

    # Empty rejected
    with pytest.raises(ValidationError):
        AskRequest(question="")

    # Too long rejected (> 500 chars)
    with pytest.raises(ValidationError):
        AskRequest(question="a" * 501)


def test_user_settings_validation():
    # Valid
    settings = UserSettings(
        briefing_time="07:30",
        sections=["tech", "economy"],
        verified_only_default=True,
    )
    assert settings.briefing_time == "07:30"
    assert settings.verified_only_default is True

    # Invalid briefing_time ("25:99")
    with pytest.raises(ValidationError):
        UserSettings(
            briefing_time="25:99",
            sections=["tech"],
            verified_only_default=False,
        )

    # Empty sections list rejected
    with pytest.raises(ValidationError):
        UserSettings(
            briefing_time="08:00",
            sections=[],
            verified_only_default=False,
        )

    # Sections are the known ones only (was `Section | str`: any string, any length)
    with pytest.raises(ValidationError):
        UserSettings(briefing_time="08:00", sections=["tech", "x" * 5000])

    # Unknown fields are refused
    with pytest.raises(ValidationError):
        UserSettings(briefing_time="08:00", sections=["tech"], owner_login="evil")

    # Weekly targets are bounded minutes
    with pytest.raises(ValidationError):
        UserSettings(briefing_time="08:00", sections=["tech"], weekly_targets_min={"dev": -1})


def test_ask_request_strips_and_refuses_blank():
    assert AskRequest(question="  What is CRR?  ").question == "What is CRR?"
    for blank in ("   ", "\n\t"):
        with pytest.raises(ValidationError):
            AskRequest(question=blank)
    with pytest.raises(ValidationError):
        AskRequest(question="q", chat_id=5)  # no extra fields reach the job


def test_today_response_serialization():
    item = TodayItem(
        cluster_id="101",
        title="Headline Title",
        section="india",
        exam_tags=["GATE", "UPSC"],
        verified_headline=True,
        four_questions={"why": "Rates held", "how_it_affects_me": "EMIs stay"},
        note_path="notes/today.md",
    )
    resp = TodayResponse(
        date=date(2026, 11, 15),
        items=[item],
        plan_lines=["Review compiler design", "Read economy chapter"],
    )
    data = resp.model_dump()
    assert data["date"] == date(2026, 11, 15)
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Headline Title"


def test_quiz_question_and_outcome():
    qq = QuizQuestion(
        mcq_id=1,
        question="Which layer performs routing?",
        options=["Transport", "Network", "Data Link", "Physical"],
    )
    assert qq.mcq_id == 1
    assert len(qq.options) == 4

    outcome = AnswerOutcome(
        correct=True,
        correct_index=1,
        explanation="Network layer routes packets.",
        already_answered=False,
    )
    assert outcome.correct is True
    assert outcome.correct_index == 1
    # The quiz question never carries the key.
    assert "answer_index" not in QuizQuestion.model_fields
    assert "correct_index" not in QuizQuestion.model_fields


def test_ticket_schema():
    sample_token = secrets.token_hex(16)
    t = Ticket(
        id=12,
        token=sample_token,
        summary="Release document from quarantine",
        expires_at=datetime.now(UTC),
    )
    assert t.id == 12
    assert len(t.token) == 32
    assert t.token == sample_token

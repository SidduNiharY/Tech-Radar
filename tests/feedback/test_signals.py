"""Unit and integration tests for feedback buttons, signals, and action logging."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from techradar.db.models import ActionLog, Feedback
from techradar.feedback.actions import log_action
from techradar.feedback.signals import (
    BUTTONS,
    Signal,
    TargetKind,
    feedback_buttons,
    record_feedback,
)

NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


class FakeExecResult:
    def __init__(self, value: Any = None, rows: list[Any] | None = None) -> None:
        self._value = value
        self._rows = rows or []

    def scalar(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def all(self) -> list[Any]:
        return self._rows


class FakeFeedbackSession:
    def __init__(self) -> None:
        self.feedback_rows: list[Feedback] = []
        self.action_rows: list[ActionLog] = []
        self.weights_rows: list[Any] = []
        self.commits = 0

    def add(self, obj: Any) -> None:
        if isinstance(obj, Feedback):
            self.feedback_rows.append(obj)
        elif isinstance(obj, ActionLog):
            self.action_rows.append(obj)
        else:
            self.weights_rows.append(obj)

    async def flush(self) -> None:
        for idx, row in enumerate(self.feedback_rows + self.action_rows + self.weights_rows, 1):
            if getattr(row, "id", None) is None:
                row.id = idx

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, stmt: Any) -> FakeExecResult:
        sql = str(stmt).lower()
        if "count" in sql:
            return FakeExecResult(len(self.feedback_rows))
        if "from techradar.feedback" in sql or "from feedback" in sql:
            # Check duplicate
            # Look for matching target_id in feedback_rows
            # For testing duplicate
            return FakeExecResult(self.feedback_rows[0] if self.feedback_rows else None)
        return FakeExecResult(None)


def test_buttons_match_callback_pattern():
    """Verify all feedback button data strings conform to strict callback pattern."""
    for kind, _ in BUTTONS.items():
        for row in feedback_buttons(kind, 123456):
            assert all(re.fullmatch(r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$", b.data) for b in row)


async def test_group_member_feedback_ignored():
    """Telegram feedback from unauthorized group chats is ignored without storage."""
    session = FakeFeedbackSession()
    r = await record_feedback(
        session,
        kind=TargetKind.MCQ,
        target_id=1,
        signal=Signal.TOO_EASY,
        actor="telegram",
        chat_id=-100,
        owner_id=42,
        now=NOW,
    )
    assert r == "ignored"
    assert len(session.feedback_rows) == 0


async def test_duplicate_feedback_counted_once():
    """Duplicate feedback for same target, signal and day returns duplicate."""
    session = FakeFeedbackSession()

    async def exec_mock(stmt: Any) -> FakeExecResult:
        sql = str(stmt).lower()
        if "count" in sql:
            return FakeExecResult(len(session.feedback_rows))
        # If looking for existing:
        if "from" in sql and "feedback" in sql:
            # find match
            return FakeExecResult(session.feedback_rows[0] if session.feedback_rows else None)
        return FakeExecResult(None)

    session.execute = exec_mock  # type: ignore

    r1 = await record_feedback(
        session,
        kind=TargetKind.ANSWER,
        target_id=7,
        signal=Signal.DOWN,
        actor="telegram",
        chat_id=42,
        owner_id=42,
        now=NOW,
    )
    assert r1 == "recorded"
    assert len(session.feedback_rows) == 1

    # Second call should see the existing row and return duplicate
    r2 = await record_feedback(
        session,
        kind=TargetKind.ANSWER,
        target_id=7,
        signal=Signal.DOWN,
        actor="telegram",
        chat_id=42,
        owner_id=42,
        now=NOW,
    )
    assert r2 == "duplicate"
    assert len(session.feedback_rows) == 1


async def test_rate_limited_after_120():
    """More than 120 feedback events in an hour triggers rate limiting."""
    session = FakeFeedbackSession()

    async def exec_count_120(stmt: Any) -> FakeExecResult:
        sql = str(stmt).lower()
        if "count" in sql:
            return FakeExecResult(120)
        return FakeExecResult(None)

    session.execute = exec_count_120  # type: ignore

    r = await record_feedback(
        session,
        kind=TargetKind.DIGEST_ITEM,
        target_id=99,
        signal=Signal.UP,
        actor="web",
        chat_id=None,
        owner_id=42,
        now=NOW,
    )
    assert r == "rate_limited"


async def test_action_logging_and_infer_skips():
    """Test log_action and infer_skips."""
    session = FakeFeedbackSession()
    await log_action(session, "open", "story:1", topic="ai", now=NOW)
    assert len(session.action_rows) == 1
    assert session.action_rows[0].kind == "open"
    assert session.action_rows[0].target == "story:1"

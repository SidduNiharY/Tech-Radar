from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field


class GoalType(StrEnum):
    """Categorized study target goals."""

    GATE = "gate"
    SSC = "ssc"
    BANK = "bank"
    DEV = "dev"
    ENGLISH = "english"
    WORLD = "world"

    @classmethod
    def _missing_(cls, value: object) -> GoalType | None:
        if isinstance(value, str):
            val_lower = value.lower()
            for member in cls:
                if member.value == val_lower or member.name.lower() == val_lower:
                    return member
        return None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.value.lower() == other.lower()
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)


class StudySession(BaseModel):
    """Individual recorded study session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: GoalType
    duration_minutes: int = Field(gt=0)
    topics_covered: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StudyTimeTracker:
    """Tracks study sessions, aggregate durations, and daily streaks."""

    def __init__(self, sessions: list[StudySession] | None = None) -> None:
        self._sessions: list[StudySession] = list(sessions) if sessions else []

    @property
    def sessions(self) -> list[StudySession]:
        return list(self._sessions)

    def log_session(
        self,
        goal: GoalType,
        duration_minutes: int,
        topics: list[str] | None = None,
        *,
        timestamp: datetime | None = None,
        session_id: str | None = None,
    ) -> StudySession:
        """Records a study session with validation (duration_minutes > 0)."""
        if duration_minutes <= 0:
            raise ValueError(f"duration_minutes must be greater than 0, got {duration_minutes}")

        session = StudySession(
            id=session_id or str(uuid.uuid4()),
            goal=goal,
            duration_minutes=duration_minutes,
            topics_covered=list(topics) if topics is not None else [],
            timestamp=timestamp if timestamp is not None else datetime.now(UTC),
        )
        self._sessions.append(session)
        return session

    def get_total_minutes_by_goal(self) -> dict[GoalType, int]:
        """Returns cumulative study minutes per goal."""
        totals: dict[GoalType, int] = {}
        for session in self._sessions:
            totals[session.goal] = totals.get(session.goal, 0) + session.duration_minutes
        return totals

    def get_streak_days(self, reference_date: date | None = None) -> int:
        """Calculates current consecutive active study streak in days based on recorded session
        dates.
        """
        if not self._sessions:
            return 0

        recorded_dates = sorted({s.timestamp.date() for s in self._sessions})
        if not recorded_dates:
            return 0

        if reference_date is not None:
            if recorded_dates[-1] < reference_date - timedelta(days=1):
                return 0
            if recorded_dates[-1] > reference_date:
                recorded_dates = [d for d in recorded_dates if d <= reference_date]
                if not recorded_dates or recorded_dates[-1] < reference_date - timedelta(days=1):
                    return 0

        streak = 1
        current = recorded_dates[-1]
        for prev in reversed(recorded_dates[:-1]):
            if prev == current - timedelta(days=1):
                streak += 1
                current = prev
            else:
                break

        return streak

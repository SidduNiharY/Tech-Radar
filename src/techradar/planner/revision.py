from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel

from techradar.planner.schedule import StudyGoal

REVISION_OFFSETS: list[int] = [1, 7, 30, 90]


class RevisionCheckpoint(BaseModel):
    topic_id: str
    topic_title: str
    goal: StudyGoal
    due_date: date
    stage: int


class RevisionCalendar:
    """Spaced revision calendar engine based on fixed day offsets."""

    @staticmethod
    def schedule_topic_revisions(
        topic_id: str,
        topic_title: str,
        goal: StudyGoal,
        learned_date: date,
    ) -> list[RevisionCheckpoint]:
        """Calculates +1, +7, +30, and +90 day revision checkpoints."""
        return [
            RevisionCheckpoint(
                topic_id=topic_id,
                topic_title=topic_title,
                goal=goal,
                due_date=learned_date + timedelta(days=offset),
                stage=stage,
            )
            for stage, offset in enumerate(REVISION_OFFSETS, start=1)
        ]

    @staticmethod
    def get_due_revisions(
        checkpoints: list[RevisionCheckpoint],
        target_date: date,
    ) -> list[RevisionCheckpoint]:
        """Filters checkpoints due on or before target_date."""
        return [cp for cp in checkpoints if cp.due_date <= target_date]

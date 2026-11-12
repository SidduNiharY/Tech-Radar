from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel

from techradar.planner.schedule import StudyGoal

# +1, +7 and +30 for every goal; +90 only for the exam goals (Phase 5 plan,
# 06 A7.3): GATE and the government exams.
REVISION_OFFSETS: list[int] = [1, 7, 30]
EXAM_OFFSET: int = 90
EXAM_GOALS: frozenset[StudyGoal] = frozenset({StudyGoal.GATE, StudyGoal.SSC, StudyGoal.BANKING})


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
        """Revision checkpoints at +1, +7 and +30 days, plus +90 for exam goals."""
        offsets = REVISION_OFFSETS + ([EXAM_OFFSET] if goal in EXAM_GOALS else [])
        return [
            RevisionCheckpoint(
                topic_id=topic_id,
                topic_title=topic_title,
                goal=goal,
                due_date=learned_date + timedelta(days=offset),
                stage=stage,
            )
            for stage, offset in enumerate(offsets, start=1)
        ]

    @staticmethod
    def get_due_revisions(
        checkpoints: list[RevisionCheckpoint],
        target_date: date,
    ) -> list[RevisionCheckpoint]:
        """Filters checkpoints due on or before target_date."""
        return [cp for cp in checkpoints if cp.due_date <= target_date]

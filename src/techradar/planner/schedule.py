from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel


class EnergyLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StudyGoal(StrEnum):
    GATE = "gate"
    SSC = "ssc"
    BANKING = "banking"
    DEV = "dev"
    ENGLISH = "english"


class StudyBlock(BaseModel):
    id: str
    goal: StudyGoal
    title: str
    duration_minutes: int
    energy_required: EnergyLevel


class DailyPlan(BaseModel):
    date: date
    total_minutes: int
    blocks: list[StudyBlock]


_GOAL_TITLES: dict[tuple[StudyGoal, EnergyLevel], str] = {
    # HIGH: complex problem drills & new concepts
    (StudyGoal.GATE, EnergyLevel.HIGH): "GATE Complex Problem Drill & New Concepts",
    (StudyGoal.SSC, EnergyLevel.HIGH): "SSC Advanced Problem Drill & Analytical Practice",
    (StudyGoal.BANKING, EnergyLevel.HIGH): "Banking Data Interpretation & Problem Drill",
    (StudyGoal.DEV, EnergyLevel.HIGH): "DEV Deep Coding & New Architecture Drill",
    (StudyGoal.ENGLISH, EnergyLevel.HIGH): "English Advanced Essay Drill & Complex Syntax",
    # MEDIUM: reading & MCQs
    (StudyGoal.GATE, EnergyLevel.MEDIUM): "GATE Concept Reading & Practice MCQs",
    (StudyGoal.SSC, EnergyLevel.MEDIUM): "SSC General Awareness Reading & Practice MCQs",
    (StudyGoal.BANKING, EnergyLevel.MEDIUM): "Banking Sectional Reading & Practice MCQs",
    (StudyGoal.DEV, EnergyLevel.MEDIUM): "DEV Documentation Reading & Code Exploration",
    (StudyGoal.ENGLISH, EnergyLevel.MEDIUM): "English Reading Comprehension & Grammar MCQs",
    # LOW: flashcard review & vocab
    (StudyGoal.GATE, EnergyLevel.LOW): "GATE Formula Flashcard Review & Quick Recall",
    (StudyGoal.SSC, EnergyLevel.LOW): "SSC Static GK Flashcards & Quick Review",
    (StudyGoal.BANKING, EnergyLevel.LOW): "Banking Awareness Flashcards & Quick Review",
    (StudyGoal.DEV, EnergyLevel.LOW): "DEV Syntax Flashcard Review & Notes",
    (StudyGoal.ENGLISH, EnergyLevel.LOW): "English Vocabulary Flashcard Review",
}


def _get_task_title(goal: StudyGoal, energy: EnergyLevel) -> str:
    title = _GOAL_TITLES.get((goal, energy))
    if title:
        return title
    if energy == EnergyLevel.HIGH:
        return f"{goal.value.upper()} Complex Problem Drill & Concepts"
    if energy == EnergyLevel.MEDIUM:
        return f"{goal.value.upper()} Concept Reading & MCQs"
    return f"{goal.value.upper()} Flashcard Review & Vocab"


def generate_daily_plan(
    available_minutes: int,
    current_energy: EnergyLevel,
    target_goals: list[StudyGoal],
    plan_date: date | None = None,
) -> DailyPlan:
    """Generate a daily study plan balancing energy levels and targeted goals.

    - Matches available energy to appropriate tasks (HIGH -> complex problem drills/new concepts,
      MEDIUM -> reading/MCQs, LOW -> flashcard review/vocab).
    - Caps total allocated duration <= available_minutes.
    - Distributes study time evenly across targeted study goals.
    """
    target_day = plan_date or date.today()
    if available_minutes <= 0 or not target_goals:
        return DailyPlan(date=target_day, total_minutes=0, blocks=[])

    unique_goals = list(dict.fromkeys(target_goals))
    n = len(unique_goals)
    base_minutes = available_minutes // n
    remainder = available_minutes % n

    blocks: list[StudyBlock] = []
    for idx, goal in enumerate(unique_goals):
        duration = base_minutes + (1 if idx < remainder else 0)
        if duration <= 0:
            continue
        blocks.append(
            StudyBlock(
                id=f"{goal.value}-{uuid.uuid4().hex[:8]}",
                goal=goal,
                title=_get_task_title(goal, current_energy),
                duration_minutes=duration,
                energy_required=current_energy,
            )
        )

    total_allocated = sum(b.duration_minutes for b in blocks)
    return DailyPlan(date=target_day, total_minutes=total_allocated, blocks=blocks)

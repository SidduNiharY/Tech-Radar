from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class Rating(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class State(IntEnum):
    NEW = 0
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


# Standard FSRS v5 default weights
DEFAULT_WEIGHTS: tuple[float, ...] = (
    0.40255,
    1.18385,
    3.173,
    15.69105,  # w[0..3]: initial stability for Again, Hard, Good, Easy
    7.1949,
    0.5345,  # w[4..5]: initial difficulty
    1.4604,
    0.0046,  # w[6..7]: difficulty delta & mean reversion
    1.5457,
    0.1192,
    1.0192,  # w[8..10]: recall stability update
    1.9395,
    0.11,
    0.296,
    0.2269,  # w[11..14]: forget stability update
    0.2315,
    2.9898,  # w[15..16]: hard/easy stability modifiers
    0.5165,
    0.6621,  # w[17..18]: retrievability parameters
)

FACTOR: float = 19.0 / 81.0
DECAY: float = -0.5


def retrievability(
    stability: float,
    elapsed_days: float,
    factor: float = FACTOR,
    decay: float = DECAY,
) -> float:
    """Computes recall probability: (1 + factor * elapsed / stability) ^ decay."""
    if elapsed_days <= 0.0:
        return 1.0
    if stability <= 0.0:
        return 0.0
    return float((1.0 + factor * (elapsed_days / stability)) ** decay)


class Card(BaseModel):
    stability: float = 0.0
    difficulty: float = 0.0
    reps: int = 0
    lapses: int = 0
    state: State = State.NEW
    last_review: datetime | None = None
    due: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Card:
        return cls.model_validate(data)


def schedule_card(
    card: Card,
    rating: Rating,
    now: datetime,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
) -> Card:
    """Computes updated stability, difficulty, state, reps, lapses, and next due date."""
    rating_val = int(rating)

    if card.state == State.NEW:
        # Initial stability and difficulty
        init_s = weights[rating_val - 1]
        raw_d = weights[4] - math.exp(weights[5] * (rating_val - 1)) + 1.0
        init_d = min(max(raw_d, 1.0), 10.0)

        if rating == Rating.AGAIN:
            new_lapses = card.lapses + 1
            new_state = State.LEARNING
            due = now + timedelta(minutes=5)
        elif rating == Rating.HARD:
            new_lapses = card.lapses
            new_state = State.LEARNING
            due = now + timedelta(minutes=15)
        elif rating == Rating.GOOD:
            new_lapses = card.lapses
            new_state = State.REVIEW
            interval_days = max(1, round(init_s))
            due = now + timedelta(days=interval_days)
        else:  # EASY
            new_lapses = card.lapses
            new_state = State.REVIEW
            interval_days = max(1, round(init_s))
            due = now + timedelta(days=interval_days)

        return Card(
            stability=round(init_s, 4),
            difficulty=round(init_d, 4),
            reps=card.reps + 1,
            lapses=new_lapses,
            state=new_state,
            last_review=now,
            due=due,
        )

    # For review / learning / relearning cards
    if card.last_review is None:
        elapsed_days = 0.0
    else:
        lr = card.last_review
        curr = now
        if lr.tzinfo is not None and curr.tzinfo is None:
            curr = curr.replace(tzinfo=lr.tzinfo)
        elif lr.tzinfo is None and curr.tzinfo is not None:
            lr = lr.replace(tzinfo=curr.tzinfo)
        elapsed_days = max(0.0, (curr - lr).total_seconds() / 86400.0)

    r = retrievability(card.stability, elapsed_days)

    # Difficulty update with mean reversion
    delta_d = -weights[6] * (rating_val - 3)
    d0_good = weights[4] - math.exp(weights[5] * 2.0) + 1.0
    raw_d = card.difficulty + delta_d
    next_d = weights[7] * d0_good + (1.0 - weights[7]) * raw_d
    new_d = min(max(next_d, 1.0), 10.0)

    # Stability update
    if rating == Rating.AGAIN:
        new_lapses = card.lapses + 1
        new_state = State.RELEARNING
        due = now + timedelta(minutes=5)
        s_f = (
            weights[11]
            * (new_d ** (-weights[12]))
            * (((card.stability + 1.0) ** weights[13]) - 1.0)
            * math.exp((1.0 - r) * weights[14])
        )
        new_s = max(0.1, min(s_f, card.stability))
    else:
        new_lapses = card.lapses
        h = weights[15] if rating == Rating.HARD else 1.0
        b = weights[16] if rating == Rating.EASY else 1.0
        s_r = card.stability * (
            1.0
            + math.exp(weights[8])
            * (11.0 - new_d)
            * (card.stability ** (-weights[9]))
            * (math.exp((1.0 - r) * weights[10]) - 1.0)
            * h
            * b
        )
        new_s = max(0.1, s_r)

        if rating == Rating.HARD:
            if card.state == State.REVIEW:
                new_state = State.REVIEW
                interval_days = max(1, round(new_s * 0.8))
                due = now + timedelta(days=interval_days)
            else:
                new_state = card.state
                due = now + timedelta(minutes=15)
        else:  # GOOD or EASY
            new_state = State.REVIEW
            interval_days = max(1, round(new_s))
            due = now + timedelta(days=interval_days)

    return Card(
        stability=round(new_s, 4),
        difficulty=round(new_d, 4),
        reps=card.reps + 1,
        lapses=new_lapses,
        state=new_state,
        last_review=now,
        due=due,
    )

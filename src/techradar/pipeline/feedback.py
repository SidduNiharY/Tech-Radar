"""User feedback and dynamic source weight adjustment engine."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FeedbackType(StrEnum):
    """Categorized user feedback type for pipeline and RAG outputs."""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    TOO_LONG = "too_long"
    WRONG_FACT = "wrong_fact"
    OFF_TOPIC = "off_topic"


class FeedbackRecord(BaseModel):
    """User feedback record associated with an answer, quiz, or cluster."""

    id: str
    item_id: str
    feedback_type: FeedbackType
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceWeightManager:
    """Manages source reputation weights and records regression test cases."""

    MIN_WEIGHT: float = 0.2
    MAX_WEIGHT: float = 2.0
    OFFICIAL_MIN_WEIGHT: float = 1.0
    DEFAULT_WEIGHT: float = 1.0

    def __init__(
        self,
        initial_weights: dict[str, float] | None = None,
        official_domains: set[str] | list[str] | None = None,
    ) -> None:
        self._weights: dict[str, float] = (
            {k.strip().lower(): float(v) for k, v in initial_weights.items()}
            if initial_weights
            else {}
        )
        self._official_domains: set[str] = (
            {d.strip().lower() for d in official_domains}
            if official_domains is not None
            else {"pib.gov.in", "rbi.org.in"}
        )
        self._regression_cases: list[dict[str, Any]] = []

    @property
    def weights(self) -> dict[str, float]:
        """Return a snapshot of current source weights."""
        return dict(self._weights)

    @property
    def regression_cases(self) -> list[dict[str, Any]]:
        """Return recorded regression test cases."""
        return list(self._regression_cases)

    def get_source_weight(self, source_domain: str) -> float:
        """Get the current weight of a source domain (default: 1.0)."""
        return self._weights.get(source_domain.strip().lower(), self.DEFAULT_WEIGHT)

    def update_source_weight(
        self,
        source_domain: str,
        delta: float,
        is_official: bool = False,
    ) -> float:
        """Adjust weight by delta, clamping to bounds.

        Non-official bounds: [0.2, 2.0]. Official bounds: [1.0, 2.0].
        """
        domain = source_domain.strip().lower()
        official = is_official or (domain in self._official_domains)
        min_bound = self.OFFICIAL_MIN_WEIGHT if official else self.MIN_WEIGHT
        current = self._weights.get(domain, self.DEFAULT_WEIGHT)
        new_weight = current + delta
        clamped = max(min_bound, min(self.MAX_WEIGHT, new_weight))
        clamped = round(clamped, 4)
        self._weights[domain] = clamped
        return clamped

    def record_regression_case(
        self,
        item_id: str,
        feedback_type: FeedbackType | str,
        original_output: str,
        correction: str,
    ) -> dict[str, Any]:
        """Save regression case to prevent repeating the mistake in future pipeline runs."""
        fb_type = (
            feedback_type
            if isinstance(feedback_type, FeedbackType)
            else FeedbackType(feedback_type)
        )
        case: dict[str, Any] = {
            "id": f"reg_{uuid.uuid4().hex[:12]}",
            "item_id": str(item_id),
            "feedback_type": fb_type,
            "original_output": original_output,
            "correction": correction,
            "created_at": datetime.now(UTC),
        }
        self._regression_cases.append(case)
        return case

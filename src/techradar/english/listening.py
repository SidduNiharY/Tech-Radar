from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KeyPoints(BaseModel):
    model_config = ConfigDict(frozen=True)

    points: list[str] = Field(min_length=3, max_length=6)


class Coverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    covered: list[int]


def render_coverage(kp: KeyPoints, cov: Coverage) -> str:
    """Format comprehension coverage feedback on listening summary."""
    total = len(kp.points)
    c_set = set(cov.covered)
    covered_count = len(c_set)

    missed = [p for i, p in enumerate(kp.points) if i not in c_set]
    if missed:
        missed_str = ", ".join(missed[:3])
    else:
        missed_str = "none"

    return f"You covered {covered_count} of {total} key points. Missed: {missed_str}."

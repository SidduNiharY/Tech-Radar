"""Model test bench scoring and evaluation criteria."""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field


class BenchScore(BaseModel):
    """Result of an evaluation bench scoring run."""

    total: int = Field(..., description="Total number of evaluated test items")
    correct: int = Field(..., description="Number of correctly matching items")
    accuracy: float = Field(..., description="Proportion of items matching (0.0 to 1.0)")
    mismatches: list[int] = Field(
        default_factory=list, description="0-based indices of items that did not match"
    )


def score_bench_run(expected: Sequence[str], actual: Sequence[str]) -> BenchScore:
    """Score model outputs against ground truth expected outputs.

    Compares strings after stripping leading/trailing whitespace and normalising case.
    Raises ValueError if expected and actual sequences have differing lengths.
    """
    if len(expected) != len(actual):
        msg = f"Sequences must have the same length: {len(expected)} vs {len(actual)}"
        raise ValueError(msg)

    if not expected:
        return BenchScore(total=0, correct=0, accuracy=0.0, mismatches=[])

    correct = 0
    mismatches: list[int] = []

    for idx, (exp, act) in enumerate(zip(expected, actual, strict=True)):
        if exp.strip().casefold() == act.strip().casefold():
            correct += 1
        else:
            mismatches.append(idx)

    accuracy = correct / len(expected)
    return BenchScore(
        total=len(expected),
        correct=correct,
        accuracy=round(accuracy, 4),
        mismatches=mismatches,
    )


def passes_worker(m: Mapping[str, float]) -> bool:
    """Worker role pass threshold: tag agreement >= 90% and first-try JSON validity >= 98%."""
    tag_agreement = m.get("tag_agreement", 0.0)
    json_first_try = m.get("json_first_try", 0.0)
    return tag_agreement >= 0.90 and json_first_try >= 0.98


def passes_checker(m: Mapping[str, float]) -> bool:
    """Checker role pass threshold: wrong-key catch >= 90% and false-flag rate <= 5%."""
    wrong_key_catch = m.get("wrong_key_catch", 0.0)
    false_flag = m.get("false_flag", 1.0)
    return wrong_key_catch >= 0.90 and false_flag <= 0.05


def passes_embed(m: Mapping[str, float]) -> bool:
    """Embedding model pass threshold from Phase 2b RAG specifications."""
    hit_rate = m.get("hit_rate_at_5", m.get("hit_rate", 0.0))
    mrr = m.get("mrr", 0.0)
    return hit_rate >= 0.80 and mrr >= 0.70


def passes_night(votes: Sequence[bool]) -> bool:
    """Night-window blind A/B evaluation: candidate preferred in at least 2 of 3 prompts."""
    return sum(1 for vote in votes if vote) >= 2

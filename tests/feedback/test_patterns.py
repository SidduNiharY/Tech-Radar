"""Unit tests for pattern detection rules and candidate filtering."""

from __future__ import annotations

from typing import Any

from techradar.db.models import PreferenceRule
from techradar.feedback.patterns import (
    Mode,
    StyleProposal,
    edit_candidates,
    find_patterns,
    frequency_candidates,
    mistakes_candidates,
    sequence_candidates,
    time_candidates,
)


def skips(skip_count: int, of: int, topic: str = "crypto") -> list[dict[str, Any]]:
    """Helper creating a list of items with specified skip counts."""
    items: list[dict[str, Any]] = []
    for i in range(of):
        is_skip = i < skip_count
        items.append(
            {
                "id": i + 1,
                "topic": topic,
                "kind": "skip" if is_skip else "open",
            }
        )
    return items


def answers_followed_by(
    text: str,
    match_count: int,
    of: int,
    mode: str = "gate",
) -> list[dict[str, Any]]:
    """Helper creating answer follow-up sequence items."""
    items: list[dict[str, Any]] = []
    for i in range(of):
        txt = text if i < match_count else "ok thanks"
        items.append(
            {
                "id": i + 1,
                "mode": mode,
                "text": txt,
            }
        )
    return items


def edit(removed: list[str]) -> dict[str, Any]:
    """Helper creating mock edit item with removed sections."""
    return {
        "sections_removed": removed,
        "length_change": -50,
    }


def test_frequency_rule_needs_ten_items():
    """Frequency rule requires at least 10 items before proposing topic down-weighting."""
    assert frequency_candidates(skips(9, of=9)) == []
    cands = frequency_candidates(skips(8, of=10))
    assert len(cands) == 1
    assert cands[0].evidence.count == 8
    assert cands[0].evidence.total == 10
    assert cands[0].proposal.kind == "topic"


def test_sequence_rule_example_follow_ups():
    """Sequence rule proposes adding an example when user repeatedly asks for one."""
    cands = sequence_candidates(answers_followed_by("give me an example", 6, of=10, mode="gate"))
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c.proposal, StyleProposal)
    assert c.proposal.mode == Mode.GATE
    assert (c.proposal.field, c.proposal.value) == ("examples", "one")


def test_edit_rule_skip_section():
    """Edit rule proposes skip_section when user repeatedly deletes the same heading."""
    cands = edit_candidates([edit(removed=["Background"])] * 5)
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c.proposal, StyleProposal)
    assert (c.proposal.field, c.proposal.value) == ("skip_section", "Background")


def test_mistakes_candidates():
    """Repeated mistakes on same subject trigger focused_revision candidate."""
    mistakes = [
        {"id": 1, "subject": "Indian Polity - Fundamental Rights"},
        {"id": 2, "subject": "Indian Polity - Fundamental Rights"},
        {"id": 3, "subject": "Indian Polity - Fundamental Rights"},
    ]
    cands = mistakes_candidates(mistakes)
    assert len(cands) == 1
    assert cands[0].proposal.kind == "focused_revision"
    assert "Fundamental Rights" in cands[0].proposal.subject


def test_time_candidates_median():
    """Session durations map to nearest standard block minute (25, 45, 60)."""
    sessions = [{"id": i, "minutes": 42.0} for i in range(7)]
    cands = time_candidates(sessions)
    assert len(cands) == 1
    assert cands[0].proposal.field == "block_minutes"
    assert cands[0].proposal.value == "45"


class FakePatternSession:
    def __init__(self, active_rules: list[PreferenceRule] | None = None) -> None:
        self.active_rules = active_rules or []

    async def execute(self, stmt: Any) -> Any:
        class Res:
            def __init__(self, items: list[Any]) -> None:
                self.items = items

            def scalars(self) -> Any:
                return self

            def all(self) -> list[Any]:
                return self.items

        return Res(self.active_rules)


async def test_candidate_dropped_when_rule_active():
    """Candidates whose proposals are already active are filtered out."""
    rule = PreferenceRule(
        mode=Mode.GATE.value,
        field="examples",
        value="one",
        evidence={},
        status="active",
    )
    session = FakePatternSession(active_rules=[rule])
    patterns = await find_patterns(session)
    assert patterns == []

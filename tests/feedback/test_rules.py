"""Unit tests for style rule constraints, model candidate selection and link safety."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from techradar.feedback.patterns import (
    Evidence,
    Mode,
    PatternCandidate,
    WeightProposal,
)
from techradar.feedback.rules import (
    StyleRule,
    choose_and_word,
)

CANDIDATE = PatternCandidate(
    kind="source",
    subject="Source x",
    evidence=Evidence(ids=[1, 2, 3], count=3, total=None, window_days=14, table="feedback"),
    proposal=WeightProposal(kind="source", key="source:x", target=0.5),
)


class FakeCompleter:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    async def complete(self, *args, **kwargs) -> str:
        return self.responses.pop(0)


def test_style_rule_rejects_unknown_value_and_protected_sections():
    """StyleRule enforces strict allowed values and forbids skipping protected sections."""
    with pytest.raises(ValidationError):
        StyleRule(mode=None, field="length", value="tiny")

    with pytest.raises(ValidationError):
        StyleRule(mode=Mode.NEWS, field="skip_section", value="What critics say")

    # Valid rules pass
    r1 = StyleRule(mode=None, field="length", value="short")
    assert r1.value == "short"

    r2 = StyleRule(mode=Mode.GATE, field="order", value="formula_first")
    assert r2.value == "formula_first"


async def test_model_cannot_change_the_proposal():
    """Model only selects candidate index and wording; the proposal remains immutable."""
    completer = FakeCompleter(
        ['{"picks": [{"candidate_index": 0, "wording": "Show less crypto news"}]}']
    )
    picks = await choose_and_word(completer, [CANDIDATE])
    assert len(picks) == 1
    assert picks[0].candidate_index == 0
    assert picks[0].wording == "Show less crypto news"


async def test_link_in_wording_rejected():
    """Any suggestion with web links is strictly rejected."""
    completer = FakeCompleter(
        [
            '{"picks": [{"candidate_index": 0, "wording": "see https://example.com/more"}]}',
            '{"picks": [{"candidate_index": 0, "wording": "see https://example.com/more"}]}',
        ]
    )
    picks = await choose_and_word(completer, [CANDIDATE])
    assert picks == []

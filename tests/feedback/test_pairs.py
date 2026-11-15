"""Unit tests for Which-is-better comparison pairs and limit enforcement."""

from __future__ import annotations

import re
from typing import Any

from techradar.db.models import PreferencePair
from techradar.feedback.pairs import (
    VARIANTS,
    create_pair,
    format_pair_message,
    make_pair,
    pair_due,
    record_pair_choice,
)


def test_pair_due_limits():
    """Verify weekly (<3) and daily (<1) frequency caps for pairs."""
    assert pair_due(0, 0) is True
    assert pair_due(3, 0) is False
    assert pair_due(1, 1) is False
    assert pair_due(2, 0) is True


class FakeCompleter:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    async def complete(self, *args, **kwargs) -> str:
        return self.responses.pop(0)


async def test_make_pair_needs_both_answers_cited():
    """make_pair returns None if either generated answer lacks valid citations."""
    # Case 1: First answer cited, second answer uncited -> returns None
    completer_bad = FakeCompleter(
        [
            '{"text": "Short answer here [C1]", "citations": ["[C1]"]}',
            '{"text": "Detailed answer without citations", "citations": []}',
        ]
    )
    res_bad = await make_pair(completer_bad, "What is CRR?", ["doc excerpt"], VARIANTS[0])
    assert res_bad is None

    # Case 2: Both answers cited -> returns tuple
    completer_good = FakeCompleter(
        [
            '{"text": "Short answer here [C1]", "citations": ["[C1]"]}',
            '{"text": "Detailed answer here with citations [C2]", "citations": ["[C2]"]}',
        ]
    )
    res_good = await make_pair(completer_good, "What is CRR?", ["doc excerpt"], VARIANTS[0])
    assert res_good is not None
    assert len(res_good) == 2
    assert "Short answer" in res_good[0]
    assert "Detailed answer" in res_good[1]


def test_format_pair_message_buttons():
    """Verify pair message formatting and callback data regex match."""
    msg, buttons = format_pair_message(
        question="What is repo rate?",
        ans_a="Version A [C1]",
        ans_b="Version B [C1]",
        pair_id=123,
    )
    assert msg.startswith("Which is better?\nA: Version A")
    assert len(buttons) == 1
    assert len(buttons[0]) == 3
    for b in buttons[0]:
        assert re.fullmatch(r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$", b.data)
    assert buttons[0][0].data == "pair:123:1"
    assert buttons[0][1].data == "pair:123:2"
    assert buttons[0][2].data == "pair:123:3"


class FakePairSession:
    def __init__(self) -> None:
        self.pairs: list[PreferencePair] = []

    def add(self, obj: Any) -> None:
        if isinstance(obj, PreferencePair):
            self.pairs.append(obj)

    async def flush(self) -> None:
        for idx, p in enumerate(self.pairs, 1):
            if getattr(p, "id", None) is None:
                p.id = idx

    async def execute(self, stmt: Any) -> Any:
        class Res:
            def __init__(self, p: PreferencePair | None) -> None:
                self.p = p

            def scalar_one_or_none(self) -> Any:
                return self.p

        return Res(self.pairs[0] if self.pairs else None)


async def test_create_and_record_choice():
    """Verify pair creation in database and subsequent choice recording."""
    session = FakePairSession()
    pid = await create_pair(
        session,
        mode="gate",
        question="What is scheduling?",
        version_a="A [C1]",
        version_b="B [C1]",
        variant_a="short",
        variant_b="detailed",
    )
    assert pid == 1
    assert session.pairs[0].chosen is None

    await record_pair_choice(session, pair_id=1, chosen="a")
    assert session.pairs[0].chosen == "a"
    assert session.pairs[0].answered_at is not None

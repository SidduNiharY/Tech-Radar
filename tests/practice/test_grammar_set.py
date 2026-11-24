"""The grammar set the owner asks for with /grammar, and how its answers are handled."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from techradar.db.models import GrammarItem as DBGrammarItem
from techradar.db.models import Mistake
from techradar.practice import grammar
from techradar.practice.grammar import answer_grammar, render_grammar_item, run_grammar_set

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)


def test_render_grammar_item_buttons_match_callback_shape():
    text, kb = render_grammar_item(9, "She has ___ degree.", ["a", "an", "the", "no"], 1, 10)
    assert text.startswith("G1/10 · She has ___ degree.")
    assert [b.data for b in kb[0]] == [f"gram:9:{i}" for i in range(4)]


async def test_run_grammar_set_enqueues_one_message_per_item(monkeypatch: pytest.MonkeyPatch):
    rows = [
        SimpleNamespace(id=i, prompt=f"Prompt number {i} here", options=list("abcd"))
        for i in (3, 2)
    ]
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    send = AsyncMock()
    monkeypatch.setattr(grammar, "enqueue_message", send)
    assert await run_grammar_set(session, now=NOW, owner_chat_id=42) == 2
    assert [c.kwargs["ref_id"] for c in send.await_args_list] == [3, 2]
    assert all(c.kwargs["chat_id"] == 42 for c in send.await_args_list)


@pytest.mark.db
async def test_wrong_grammar_answer_is_noted_once_a_day(session):
    item = DBGrammarItem(
        kind="fill_blank",
        prompt="She has ___ university degree.",
        options=["a", "an", "the", "no article"],
        answer_index=0,
        rule="articles",
        explanation="Use a before a consonant sound.",
    )
    session.add(item)
    await session.flush()
    assert await answer_grammar(session, item.id, 0, NOW) == "✅ Correct."
    first = await answer_grammar(session, item.id, 1, NOW)
    assert first.startswith("❌ Answer: A. a")
    await answer_grammar(session, item.id, 2, NOW)
    rows = (await session.execute(select(Mistake).where(Mistake.kind == "grammar"))).scalars().all()
    assert len(rows) == 1
    assert await answer_grammar(session, item.id + 999, 0, NOW) is None

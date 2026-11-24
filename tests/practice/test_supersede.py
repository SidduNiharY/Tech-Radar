from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from sqlalchemy import select

from techradar.db.models import MCQ, Fact, FactChange, Flashcard, Outbox
from techradar.messaging import outbox as outbox_mod
from techradar.practice import supersede
from techradar.practice.supersede import apply_fact_change, run_fact_changes


@pytest.mark.asyncio
async def test_apply_fact_change_nonexistent():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    res = await apply_fact_change(session, 99999, {}, owner_chat_id=1, now=datetime.now(UTC))
    assert res == (0, 0)


@pytest.mark.asyncio
async def test_apply_fact_change_already_notified():
    session = AsyncMock()
    change = SimpleNamespace(id=1, notified_at=datetime.now(UTC))
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = change
    session.execute.return_value = mock_res

    res = await apply_fact_change(session, 1, {}, owner_chat_id=1, now=datetime.now(UTC))
    assert res == (0, 0)


@pytest.mark.db
@pytest.mark.asyncio
async def test_superseded_fact_retires_mcqs_and_cards(session):
    now = datetime.now(UTC)

    # Old and new facts
    old_fact = Fact(
        fact_key="rbi_repo_rate_old",
        statement="RBI repo rate is 5.5%.",
        subject="RBI",
        value="5.5%",
        section="economy",
        status="superseded",
        subject_key="rbi.repo_rate",
    )
    new_fact = Fact(
        fact_key="rbi_repo_rate_new",
        statement="RBI repo rate is 5.25%.",
        subject="RBI",
        value="5.25%",
        section="economy",
        status="verified",
        subject_key="rbi.repo_rate",
    )
    session.add_all([old_fact, new_fact])
    await session.flush()

    change = FactChange(
        subject_key="rbi.repo_rate",
        old_fact_id=old_fact.id,
        new_fact_id=new_fact.id,
        old_value="5.5%",
        new_value="5.25%",
    )
    session.add(change)
    await session.flush()

    # Active MCQ from old fact
    mcq = MCQ(
        fact_id=old_fact.id,
        question="What is the RBI repo rate?",
        options=["5.5%", "6.0%", "5.0%", "4.5%"],
        answer_index=0,
        explanation="RBI set rate at 5.5%.",
        status="active",
    )
    session.add(mcq)
    await session.flush()

    # Active Flashcard from old fact
    card1 = Flashcard(
        front="What is the current Repo Rate?",
        back="The Repo Rate is 5.5%",
        source_kind="fact",
        source_id=old_fact.id,
        due=now,
        fsrs_card={},
        retired=False,
    )
    # Active Flashcard from old MCQ
    card2 = Flashcard(
        front="MCQ Card: Repo Rate",
        back="Repo rate answer: 5.5%",
        source_kind="mcq",
        source_id=mcq.id,
        due=now,
        fsrs_card={},
        retired=False,
    )
    session.add_all([card1, card2])
    await session.flush()

    mcqs_retired, cards_retired = await apply_fact_change(
        session, change.id, {"rbi.repo_rate": "Repo rate"}, owner_chat_id=42, now=now
    )
    sent = (await session.execute(select(Outbox).where(Outbox.purpose == "fact_change"))).scalars()
    assert [m.text for m in sent] == ["Repo rate changed: 5.5% → 5.25%. Old cards updated."]
    assert mcqs_retired == 1
    assert cards_retired == 2

    # Verify DB state
    mcq_db = (await session.execute(select(MCQ).where(MCQ.id == mcq.id))).scalar_one()
    assert mcq_db.status == "retired"

    c1_db = (await session.execute(select(Flashcard).where(Flashcard.id == card1.id))).scalar_one()
    assert c1_db.retired is True

    c2_db = (await session.execute(select(Flashcard).where(Flashcard.id == card2.id))).scalar_one()
    assert c2_db.retired is True

    ch_db = (
        await session.execute(select(FactChange).where(FactChange.id == change.id))
    ).scalar_one()
    assert ch_db.notified_at is not None


@pytest.mark.db
@pytest.mark.asyncio
async def test_change_notified_once(session):
    now = datetime.now(UTC)
    old = Fact(
        fact_key="k-o",
        statement="Repo 5.5%.",
        subject="RBI",
        value="5.5%",
        section="economy",
        status="superseded",
        subject_key="rbi.repo_rate",
    )
    new = Fact(
        fact_key="k-n",
        statement="Repo 5.25%.",
        subject="RBI",
        value="5.25%",
        section="economy",
        status="verified",
        subject_key="rbi.repo_rate",
    )
    session.add_all([old, new])
    await session.flush()
    session.add(
        FactChange(
            subject_key="rbi.repo_rate",
            old_fact_id=old.id,
            new_fact_id=new.id,
            old_value="5.5%",
            new_value="5.25%",
        )
    )
    await session.flush()
    first = await run_fact_changes(
        session, {"rbi.repo_rate": "Repo rate"}, owner_chat_id=42, now=now
    )
    second = await run_fact_changes(
        session, {"rbi.repo_rate": "Repo rate"}, owner_chat_id=42, now=now
    )
    assert len(first) >= 1 and second == []
    texts = (
        (await session.execute(select(Outbox.text).where(Outbox.purpose == "fact_change")))
        .scalars()
        .all()
    )
    assert texts.count("Repo rate changed: 5.5% → 5.25%. Old cards updated.") == 1


async def test_notice_goes_through_the_real_enqueue_signature(monkeypatch):
    """The first run called enqueue_message(session, msg): autospec rejects a wrong call."""
    spy = create_autospec(outbox_mod.enqueue_message, return_value=1)
    monkeypatch.setattr(supersede, "enqueue_message", spy)
    change = SimpleNamespace(
        id=7,
        notified_at=None,
        old_fact_id=1,
        subject_key="rbi.repo_rate",
        old_value="5.5%",
        new_value="5.25%",
    )
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    first = MagicMock()
    first.scalar_one_or_none.return_value = change
    session = AsyncMock()
    session.execute.side_effect = [first, empty, empty]
    now = datetime(2026, 11, 22, tzinfo=UTC)
    res = await apply_fact_change(
        session, 7, {"rbi.repo_rate": "Repo rate"}, owner_chat_id=42, now=now
    )
    assert res == (0, 0)
    spy.assert_awaited_once_with(
        session,
        chat_id=42,
        text="Repo rate changed: 5.5% → 5.25%. Old cards updated.",
        purpose="fact_change",
        ref_id=7,
    )
    assert change.notified_at == now

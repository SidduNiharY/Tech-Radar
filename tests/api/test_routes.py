"""Phase 4 Task 2 routes against the real database (marker `db`, server only).

SEC: SEC-18, SEC-27, SEC-41, SEC-54. Run with `make test-db`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from techradar.db.models import MCQ, Briefing, Chunk, Flashcard, Plan, UserSettings
from techradar.db.models import Answer as AnswerRow
from techradar.settings import Settings
from tests.api.conftest import AUTH, NOW, FakeDefer
from tests.api.dbutil import CHUNK_PREFIX, db_client, may_wipe, run_db, wipe

pytestmark = pytest.mark.db


@pytest.fixture
def fake_defer() -> FakeDefer:
    return FakeDefer()


@pytest.fixture
def client(settings: Settings, fake_defer: FakeDefer) -> Iterator[TestClient]:
    may_wipe()
    wipe()
    yield db_client(settings, fake_defer)
    wipe()


async def _chunk(session: AsyncSession) -> int:
    c = Chunk(
        doc_path=f"{CHUNK_PREFIX}rbi.md",
        doc_kind="note",
        title="RBI",
        ordinal=0,
        text="The repo rate is 5.5%.",
        lang="en",
        content_hash=hashlib.sha256(b"rbi").hexdigest(),
    )
    session.add(c)
    await session.flush()
    return c.id


@pytest.fixture
def seeded_mcqs(client: TestClient) -> list[int]:
    async def seed(session: AsyncSession) -> list[int]:
        chunk_id = await _chunk(session)
        rows = [
            MCQ(
                chunk_id=chunk_id,
                question=f"Q{i}: what is the repo rate?",
                options=["4%", "5.5%", "6%", "7%"],
                answer_index=1,
                explanation="RBI held it at 5.5%.",
            )
            for i in range(3)
        ]
        session.add_all(rows)
        await session.flush()
        return [r.id for r in rows]

    return run_db(seed)


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# --- the plan's tests ---------------------------------------------------------------------


def test_ask_creates_pending_and_defers(client: TestClient, fake_defer: FakeDefer) -> None:
    r = client.post("/v1/ask", headers=AUTH, json={"question": "What did RBI decide?"})
    assert r.status_code == 200 and fake_defer.calls == [
        ("ask", {"question": "What did RBI decide?", "answer_id": r.json()["answer_id"]})
    ]

    async def row(session: AsyncSession) -> AnswerRow | None:
        return await session.get(AnswerRow, r.json()["answer_id"])

    stored = run_db(row)
    assert stored is not None and (stored.status, stored.text) == ("pending", "")
    poll = client.get(f"/v1/answers/{r.json()['answer_id']}", headers=AUTH).json()
    assert poll == {"status": "pending", "answer": None}


def test_ask_rejects_long_question(client: TestClient, fake_defer: FakeDefer) -> None:
    assert client.post("/v1/ask", headers=AUTH, json={"question": "x" * 501}).status_code == 422
    assert run_db(lambda s: _count(s, AnswerRow)) == 0 and fake_defer.calls == []


def test_quiz_today_never_includes_keys(client: TestClient, seeded_mcqs: list[int]) -> None:
    body = client.get("/v1/quiz/today", headers=AUTH).json()
    assert {q["mcq_id"] for q in body} == set(seeded_mcqs)
    assert all("answer_index" not in q and "explanation" not in q for q in body)
    assert "5.5%" not in str([q["question"] for q in body])  # only in the options


def test_settings_validation(client: TestClient) -> None:
    bad = {"briefing_time": "25:99", "sections": [], "verified_only_default": False}
    assert client.put("/v1/settings", headers=AUTH, json=bad).status_code == 422
    assert run_db(lambda s: _count(s, UserSettings)) == 0


# --- more -------------------------------------------------------------------------------


def test_answer_after_the_worker_fills_it(client: TestClient) -> None:
    async def answered(session: AsyncSession) -> int:
        row = AnswerRow(
            chat_id=1,
            question="q?",
            text="Held at 5.5% [C1].",
            status="answered",
            citations=[
                {"n": 1, "doc_path": "wiki/rbi.md", "title": "RBI", "heading": "", "verified": True}
            ],
        )
        session.add(row)
        await session.flush()
        return row.id

    answer_id = run_db(answered)
    body = client.get(f"/v1/answers/{answer_id}", headers=AUTH).json()
    assert body["status"] == "answered"
    assert body["answer"]["citations"][0]["doc_path"] == "wiki/rbi.md"
    assert client.post(f"/v1/answers/{answer_id}/save", headers=AUTH).status_code == 202


def test_quiz_answer_records_once_and_shows_the_key(
    client: TestClient, seeded_mcqs: list[int]
) -> None:
    mcq_id = seeded_mcqs[0]
    first = client.post(f"/v1/quiz/{mcq_id}/answer", headers=AUTH, json={"chosen": 0}).json()
    assert first == {
        "correct": False,
        "correct_index": 1,
        "explanation": "RBI held it at 5.5%.",
        "already_answered": False,
    }
    again = client.post(f"/v1/quiz/{mcq_id}/answer", headers=AUTH, json={"chosen": 1}).json()
    assert again["already_answered"] is True and again["correct"] is False
    assert run_db(lambda s: _count(s, Flashcard)) == 1  # the wrong answer became a card


def test_cards_due_back_and_rate_once(client: TestClient) -> None:
    async def card(session: AsyncSession) -> int:
        c = Flashcard(
            front="Repo rate?", back="5.5%", source_kind="manual", due=NOW - timedelta(hours=1)
        )
        retired = Flashcard(
            front="Old", back="x", source_kind="manual", due=NOW - timedelta(days=1), retired=True
        )
        session.add_all([c, retired])
        await session.flush()
        return c.id

    card_id = run_db(card)
    assert client.get("/v1/practice/cards/due", headers=AUTH).json() == [
        {"id": card_id, "front": "Repo rate?"}
    ]
    assert client.get(f"/v1/practice/cards/{card_id}/back", headers=AUTH).json() == {"back": "5.5%"}
    r = client.post(f"/v1/practice/cards/{card_id}/rate", headers=AUTH, json={"rating": 3})
    assert r.status_code == 200 and r.json()["next_due"] > NOW.isoformat()
    # A replayed rating is refused: the card is no longer due.
    again = client.post(f"/v1/practice/cards/{card_id}/rate", headers=AUTH, json={"rating": 1})
    assert again.status_code == 409


def test_today_reads_the_latest_briefing_and_plan(client: TestClient) -> None:
    async def seed(session: AsyncSession) -> None:
        item = {
            "cluster_id": "c1",
            "title": "LangGraph 1.3 released",
            "section": "tech",
            "why": "New API",
            "verified_headline": True,
        }
        session.add(Briefing(date=date(2026, 11, 21), sent_at=NOW, items=[item, {"junk": 1}]))
        session.add(Plan(date=date(2026, 11, 22), lines=["📰 Radar (10–15 min)"]))

    run_db(seed)
    body = client.get("/v1/today", headers=AUTH).json()
    assert body["date"] == "2026-11-21"
    assert [i["title"] for i in body["items"]] == ["LangGraph 1.3 released"]
    assert body["plan_lines"] == ["📰 Radar (10–15 min)"]


def test_settings_round_trip_keeps_fields_not_sent(client: TestClient) -> None:
    full = client.get("/v1/settings", headers=AUTH).json()
    assert full["sections"] and full["exam_priority"] == ["gov", "gate"]
    put = {"briefing_time": "07:15", "sections": ["tech", "economy"], "verified_only_default": True}
    body = client.put("/v1/settings", headers=AUTH, json=put).json()
    assert (body["briefing_time"], body["sections"]) == ("07:15", ["tech", "economy"])
    assert body["weekly_targets_min"] == full["weekly_targets_min"]
    assert client.get("/v1/settings", headers=AUTH).json() == body


def test_read_only_role_cannot_write_through_a_get_session() -> None:
    """GET routes use tr_ro: even a buggy GET cannot change a row (SEC-54)."""
    may_wipe()

    async def write(session: AsyncSession) -> None:
        session.add(UserSettings(key="briefing_time", value="05:00"))
        await session.flush()

    with pytest.raises(DBAPIError, match="permission denied"):
        run_db(write, role="ro")

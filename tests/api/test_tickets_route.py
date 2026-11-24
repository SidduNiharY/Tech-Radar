"""`POST /v1/tickets/confirm` against the real database (marker `db`). SEC-56.

A real held library doc is released through a ticket: once, in its own tab only, never
after it expired.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from techradar.db.models import LibraryDoc, QuarantineItem
from techradar.library.quarantine import release_prompt
from techradar.settings import Settings
from techradar.tickets import create_ticket
from tests.api.conftest import AUTH, NOW, FakeDefer
from tests.api.dbutil import db_client, may_wipe, run_db, wipe

pytestmark = pytest.mark.db

TAB = "tab0123456789abcdef"
OTHER_TAB = "tabffffffffffffffff"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    may_wipe()
    wipe()
    yield db_client(settings, FakeDefer())
    wipe()


@pytest.fixture
def held_doc(client: TestClient) -> Iterator[tuple[int, int]]:
    sha = os.urandom(32).hex()

    async def seed(session: AsyncSession) -> tuple[int, int]:
        doc = LibraryDoc(
            sha256=sha, title="Macro Book", kind="docx", origin="library",
            original_path=f"originals/{sha}.docx", size_bytes=10, status="quarantined",
            trust="my_own",
        )  # fmt: skip
        session.add(doc)
        await session.flush()
        item = QuarantineItem(
            job_id=os.urandom(16).hex(), path=f"/data/quarantine/x/{sha}.docx", origin="library",
            reasons=["macros"],
        )  # fmt: skip
        session.add(item)
        await session.flush()
        return doc.id, item.id

    ids = run_db(seed)
    yield ids

    async def clean(session: AsyncSession) -> None:
        await session.execute(delete(QuarantineItem).where(QuarantineItem.id == ids[1]))
        await session.execute(delete(LibraryDoc).where(LibraryDoc.id == ids[0]))

    run_db(clean)


def _ticket(item_id: int, tab: str = TAB, at=NOW) -> str:
    async def make(session: AsyncSession) -> str:
        text = await release_prompt(session, item_id)
        assert text is not None and text.startswith("Release Macro Book?")
        t = await create_ticket(
            session, session_id=f"web:{tab}", channel="web", action="quarantine.release",
            args={"id": item_id}, summary=text, now=at,
        )  # fmt: skip
        return t.token

    return run_db(make)


def _confirm(client: TestClient, token: str, tab: str = TAB) -> dict[str, object]:
    headers = {**AUTH, "X-TR-Session": tab}
    return client.post("/v1/tickets/confirm", headers=headers, json={"token": token}).json()


def test_release_through_a_ticket_runs_once(client: TestClient, held_doc) -> None:
    doc_id, item_id = held_doc
    token = _ticket(item_id)
    assert _confirm(client, token, OTHER_TAB) == {"result": "wrong_session", "message": None}
    assert _confirm(client, token) == {
        "result": "ok",
        "message": "Released. It will be processed as flagged.",
    }
    assert _confirm(client, token) == {"result": "used", "message": None}

    async def state(session: AsyncSession) -> tuple[object, object]:
        doc = await session.get(LibraryDoc, doc_id)
        item = await session.get(QuarantineItem, item_id)
        assert doc is not None and item is not None
        return doc.flagged, item.released_at

    flagged, released_at = run_db(state)
    assert flagged is True and released_at is not None


def test_expired_ticket_releases_nothing(client: TestClient, held_doc) -> None:
    doc_id, item_id = held_doc
    token = _ticket(item_id, at=NOW - timedelta(seconds=61))
    assert _confirm(client, token)["result"] == "expired"

    async def flagged(session: AsyncSession) -> bool:
        doc = await session.get(LibraryDoc, doc_id)
        return bool(doc and doc.flagged)

    assert run_db(flagged) is False


def test_unknown_token(client: TestClient) -> None:
    assert _confirm(client, "0" * 32) == {"result": "unknown", "message": None}

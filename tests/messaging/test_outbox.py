"""Tests for outbox messaging and callback parsing (Phase 2b Task 6).

SEC: SEC-26, SEC-37, SEC-39, SEC-41.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.messaging.outbox import Button, enqueue_message, parse_callback, send_pending
from techradar.settings import Settings


def test_parse_callback() -> None:
    assert parse_callback("save_answer:12") == ("save_answer", [12])
    assert parse_callback("save_answer:12:3") == ("save_answer", [12, 3])
    assert parse_callback("save_answer:abc") is None
    assert parse_callback("x" * 100) is None
    assert parse_callback("") is None


def test_button_model() -> None:
    b = Button(text="Save", data="save_answer:42")
    assert b.text == "Save"
    assert b.data == "save_answer:42"


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
        link_preview_options: Any = None,
    ) -> Any:
        disabled = getattr(link_preview_options, "is_disabled", False)
        self.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
                "link_preview_disabled": disabled,
            }
        )

        class FakeSentMsg:
            message_id = len(self.sent)

        return FakeSentMsg()


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def outbox_session_factory(
    db_settings: Settings,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    app_engine = make_engine("app", db_settings)
    session_factory = async_sessionmaker(app_engine, expire_on_commit=False)

    async with session_factory() as session:
        await session.execute(text("DELETE FROM techradar.outbox WHERE chat_id = 42"))
        await session.commit()

    try:
        yield session_factory
    finally:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM techradar.outbox WHERE chat_id = 42"))
            await session.commit()
        await app_engine.dispose()


@pytest.mark.db
async def test_enqueue_and_send_marks_sent(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_bot = FakeBot()
    async with outbox_session_factory() as session:
        await enqueue_message(session, 42, "hi", purpose="answer")
        await session.commit()

    sent_count = await send_pending(fake_bot, outbox_session_factory)
    assert sent_count == 1
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["link_preview_disabled"] is True
    assert fake_bot.sent[0]["text"] == "hi"

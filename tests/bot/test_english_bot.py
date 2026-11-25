"""Phase 6 routing and bot handlers: owner only, nothing else gets through (SEC-26)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot.english_commands import (
    handle_essay_reply,
    handle_polish,
    handle_reflection_reply,
    handle_story,
    story_is_open,
)
from techradar.bot.routing import Routed, route_update
from techradar.worker.names import ESSAY_REPLY, POLISH, REFLECTION_SAVE

OWNER = 42
GROUP = 99


def test_polish_and_story_are_owner_only() -> None:
    assert route_update(OWNER, "/polish me go", OWNER) == Routed("polish", "me go")
    assert route_update(OWNER, "/story", OWNER) == Routed("story", "")
    assert route_update(GROUP, "/polish x", OWNER, group_ids={GROUP}) == Routed("ignore")
    assert route_update(GROUP, "/story", OWNER, group_ids={GROUP}) == Routed("ignore")
    assert route_update(7, "/polish x", OWNER) == Routed("ignore")


def test_essay_and_reflection_replies_only_from_the_owner() -> None:
    kw = {"reply_to_purpose": "essay", "reply_to_ref": 1}
    assert route_update(OWNER, "My essay", OWNER, **kw) == Routed("essay_reply", "My essay")
    assert route_update(GROUP, "My essay", OWNER, group_ids={GROUP}, **kw) == Routed("ignore")
    assert route_update(OWNER, "Went well", OWNER, reply_to_purpose="reflection") == Routed(
        "reflection_reply", "Went well"
    )


def test_story_reply_needs_an_open_draft_and_the_owner() -> None:
    assert route_update(OWNER, "I led a team", OWNER) == Routed("ignore")
    assert route_update(OWNER, "I led a team", OWNER, story_open=True) == Routed(
        "story_reply", "I led a team"
    )
    assert route_update(GROUP, "hi", OWNER, group_ids={GROUP}, story_open=True) == Routed("ignore")
    # A command is never swallowed as a story answer.
    assert route_update(OWNER, "/status", OWNER, story_open=True) == Routed("status")


def _update(date: datetime | None = None, prompt_date: datetime | None = None) -> MagicMock:
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.date = date
    update.message.reply_to_message = SimpleNamespace(date=prompt_date) if prompt_date else None
    return update


def _bot_data() -> tuple[dict, AsyncMock]:
    task = MagicMock()
    task.defer_async = AsyncMock()
    proc = MagicMock()
    proc.configure_task = MagicMock(return_value=task)
    return {"procrastinate_app": proc}, task


async def test_polish_queues_the_job_or_refuses() -> None:
    bot_data, task = _bot_data()
    update = _update()
    await handle_polish(update, bot_data, "me go home")
    bot_data["procrastinate_app"].configure_task.assert_called_with(name=POLISH)
    task.defer_async.assert_awaited_with(text="me go home")

    update = _update()
    await handle_polish(update, bot_data, "x" * 2001)
    update.message.reply_text.assert_awaited_with("Keep it under 2,000 characters.")
    update = _update()
    await handle_polish(update, {}, "hello")
    update.message.reply_text.assert_awaited_with("Not available yet.")


async def test_essay_reply_is_timed_within_30_minutes() -> None:
    sent = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
    bot_data, task = _bot_data()
    await handle_essay_reply(_update(sent + timedelta(minutes=29), sent), bot_data, 2, "text")
    bot_data["procrastinate_app"].configure_task.assert_called_with(name=ESSAY_REPLY)
    task.defer_async.assert_awaited_with(ref_id=2, text="text", timed=True)
    await handle_essay_reply(_update(sent + timedelta(hours=5), sent), bot_data, 2, "text")
    task.defer_async.assert_awaited_with(ref_id=2, text="text", timed=False)


async def test_reflection_reply_queues_the_save() -> None:
    bot_data, task = _bot_data()
    update = _update()
    await handle_reflection_reply(update, bot_data, "A good week")
    bot_data["procrastinate_app"].configure_task.assert_called_with(name=REFLECTION_SAVE)
    task.defer_async.assert_awaited_with(text="A good week")
    update.message.reply_text.assert_awaited_with("Saved your reflection.")


async def test_story_without_a_database_is_not_available() -> None:
    update = _update()
    await handle_story(update, {}, OWNER, None)
    update.message.reply_text.assert_awaited_with("Not available yet.")
    assert await story_is_open({}, OWNER) is False


@pytest.mark.parametrize("text", ["", "   "])
async def test_polish_without_text_shows_usage(text: str) -> None:
    update = _update()
    await handle_polish(update, {}, text)
    update.message.reply_text.assert_awaited_with("Send /polish followed by your text.")

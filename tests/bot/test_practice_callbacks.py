"""Phase 3 buttons and commands: owner only, validated numbers, jobs queued by name (SEC-26)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from techradar.bot import practice_callbacks as pc
from techradar.bot.callbacks import handle_callback_query
from techradar.bot.practice_commands import handle_practice_command
from techradar.practice.quiz import AnswerOutcome
from techradar.worker.names import CARDS, QUIZ

OWNER = 123


def _query(data: str, from_id: int = OWNER, chat_id: int = OWNER):
    query = MagicMock()
    query.data = data
    query.from_user.id = from_id
    query.answer = AsyncMock()
    query.message.chat.id = chat_id
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield session

    context = MagicMock()
    context.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": factory,
        "tz": "Asia/Kolkata",
    }
    return update, query, context, session


async def test_ans_records_once_and_replies_with_feedback(monkeypatch: pytest.MonkeyPatch):
    update, query, context, session = _query("ans:5:1")
    session.get = AsyncMock(return_value=SimpleNamespace(options=["a", "b", "c", "d"]))
    record = AsyncMock(
        return_value=AnswerOutcome(
            correct=False, correct_index=2, explanation="because", already_answered=False
        )
    )
    monkeypatch.setattr(pc, "record_answer", record)
    await handle_callback_query(update, context)
    assert record.await_args.args[1:3] == (5, 1)
    assert record.await_args.args[3].utcoffset().total_seconds() == 19800  # the local day
    query.message.reply_text.assert_awaited_once_with("❌ Answer: C. c — because")
    session.commit.assert_awaited_once()


async def test_ans_second_tap_adds_no_reply(monkeypatch: pytest.MonkeyPatch):
    update, query, context, session = _query("ans:5:1")
    session.get = AsyncMock(return_value=SimpleNamespace(options=["a", "b", "c", "d"]))
    monkeypatch.setattr(
        pc,
        "record_answer",
        AsyncMock(
            return_value=AnswerOutcome(
                correct=True, correct_index=1, explanation="", already_answered=True
            )
        ),
    )
    await handle_callback_query(update, context)
    query.message.reply_text.assert_not_awaited()
    query.answer.assert_awaited_once_with("Already answered today.")


async def test_ans_race_hits_the_unique_row(monkeypatch: pytest.MonkeyPatch):
    update, query, context, session = _query("ans:5:1")
    session.get = AsyncMock(return_value=SimpleNamespace(options=["a", "b", "c", "d"]))
    monkeypatch.setattr(
        pc, "record_answer", AsyncMock(side_effect=IntegrityError("x", {}, Exception()))
    )
    await handle_callback_query(update, context)
    query.answer.assert_awaited_once_with("Already answered.")


@pytest.mark.parametrize("data", ["ans:5:4", "ans:5", "rate:7:0", "rate:7:5", "card_show:1:2"])
async def test_bad_numbers_are_rejected_before_any_work(data: str, monkeypatch):
    update, query, context, session = _query(data)
    for name in ("record_answer", "rate_card", "reveal_card"):
        monkeypatch.setattr(pc, name, AsyncMock())
    await handle_callback_query(update, context)
    query.answer.assert_awaited_once_with("Invalid request.")
    query.message.reply_text.assert_not_awaited()
    pc.record_answer.assert_not_awaited()
    pc.rate_card.assert_not_awaited()


@pytest.mark.parametrize("data", ["ans:5:1", "rate:7:3", "card_show:7", "src:7"])
async def test_stranger_and_other_chat_do_nothing(data: str, monkeypatch):
    for name in ("record_answer", "rate_card", "reveal_card", "source_text"):
        monkeypatch.setattr(pc, name, AsyncMock())
    update, query, context, session = _query(data, from_id=999)
    await handle_callback_query(update, context)
    query.answer.assert_awaited_once_with()
    # the owner pressing a button of a message in some other chat is refused too
    update, query, context, session = _query(data, chat_id=-100)
    await handle_callback_query(update, context)
    query.answer.assert_awaited_once_with("Not available yet.")
    for name in ("record_answer", "rate_card", "reveal_card", "source_text"):
        getattr(pc, name).assert_not_awaited()


async def test_rate_saves_and_commits(monkeypatch: pytest.MonkeyPatch):
    update, query, context, session = _query("rate:7:3")
    rate = AsyncMock(return_value="rated")
    monkeypatch.setattr(pc, "rate_card", rate)
    await handle_callback_query(update, context)
    assert rate.await_args.args[1:3] == (7, 3)
    session.commit.assert_awaited_once()
    query.answer.assert_awaited_once_with("Saved.")


async def test_card_show_and_source_reply_in_chat(monkeypatch: pytest.MonkeyPatch):
    update, query, context, session = _query("card_show:7")
    monkeypatch.setattr(pc, "reveal_card", AsyncMock(return_value=("back", [])))
    await handle_callback_query(update, context)
    assert query.message.reply_text.await_args.args == ("back",)

    update, query, context, session = _query("src:7")
    monkeypatch.setattr(pc, "source_text", AsyncMock(return_value="From Book, p. 3:\nx"))
    await handle_callback_query(update, context)
    query.message.reply_text.assert_awaited_once_with("From Book, p. 3:\nx")


@pytest.mark.parametrize(("action", "job"), [("quiz", QUIZ), ("cards", CARDS)])
async def test_commands_queue_their_job_by_name(action: str, job: str):
    deferrer = SimpleNamespace(defer_async=AsyncMock())
    proc = MagicMock()
    proc.configure_task = MagicMock(return_value=deferrer)
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    await handle_practice_command(update, {"procrastinate_app": proc}, action)
    proc.configure_task.assert_called_once_with(name=job)
    deferrer.defer_async.assert_awaited_once_with()
    await handle_practice_command(update, {}, action)
    update.message.reply_text.assert_awaited_once_with("Not available yet.")


async def test_read_button_queues_make_chapter_cards(monkeypatch: pytest.MonkeyPatch):
    from techradar.worker.names import MAKE_CHAPTER_CARDS

    update, query, context, session = _query("read:11")
    deferrer = SimpleNamespace(defer_async=AsyncMock())
    proc = MagicMock()
    proc.configure_task = MagicMock(return_value=deferrer)
    context.application.bot_data["procrastinate_app"] = proc
    await handle_callback_query(update, context)
    proc.configure_task.assert_called_once_with(name=MAKE_CHAPTER_CARDS)
    deferrer.defer_async.assert_awaited_once_with(chapter_id=11)
    # a stranger tapping it queues nothing
    update, query, context, session = _query("read:11", from_id=999)
    context.application.bot_data["procrastinate_app"] = proc
    proc.reset_mock()
    await handle_callback_query(update, context)
    proc.configure_task.assert_not_called()


async def test_gram_button_answers_in_chat(monkeypatch: pytest.MonkeyPatch):
    update, query, context, session = _query("gram:9:1")
    monkeypatch.setattr(pc, "answer_grammar", AsyncMock(return_value="✅ Correct."))
    await handle_callback_query(update, context)
    query.message.reply_text.assert_awaited_once_with("✅ Correct.")
    session.commit.assert_awaited_once()
    update, query, context, session = _query("gram:9:7")
    await handle_callback_query(update, context)
    query.answer.assert_awaited_once_with("Invalid request.")


@pytest.mark.parametrize(("data", "keep"), [("keep:8", True), ("drop:8", False)])
async def test_keep_and_drop_decide_then_show_the_next_item(data, keep, monkeypatch):
    update, query, context, session = _query(data)
    decide = AsyncMock(return_value=True)
    monkeypatch.setattr(pc, "decide", decide)
    nxt = AsyncMock()
    monkeypatch.setattr(pc, "send_next_review", nxt)
    await handle_callback_query(update, context)
    assert decide.await_args.args[1:] == (8, keep)
    session.commit.assert_awaited_once()
    nxt.assert_awaited_once()


async def test_second_tap_on_a_review_button_does_nothing_more(monkeypatch):
    update, query, context, session = _query("keep:8")
    monkeypatch.setattr(pc, "decide", AsyncMock(return_value=False))
    nxt = AsyncMock()
    monkeypatch.setattr(pc, "send_next_review", nxt)
    await handle_callback_query(update, context)
    query.answer.assert_awaited_once_with("Already decided.")
    nxt.assert_not_awaited()


async def test_review_buttons_ignore_a_stranger(monkeypatch):
    update, query, context, session = _query("keep:8", from_id=999)
    decide = AsyncMock()
    monkeypatch.setattr(pc, "decide", decide)
    await handle_callback_query(update, context)
    decide.assert_not_awaited()


async def test_inbox_shows_the_next_item_without_link_previews(monkeypatch):
    from techradar.bot.practice_commands import handle_inbox
    from techradar.pipeline.review import ReviewItem

    update, query, context, session = _query("keep:1")
    update.message.reply_text = AsyncMock()
    monkeypatch.setattr(
        pc,
        "next_review_item",
        AsyncMock(return_value=ReviewItem(id=4, title="T", domain="d.example")),
    )
    await handle_inbox(update, context.application.bot_data)
    kwargs = update.message.reply_text.await_args.kwargs
    assert kwargs["link_preview_options"].is_disabled is True
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "keep:4"
    monkeypatch.setattr(pc, "next_review_item", AsyncMock(return_value=None))
    await handle_inbox(update, context.application.bot_data)
    assert update.message.reply_text.await_args.args == ("Nothing to review.",)

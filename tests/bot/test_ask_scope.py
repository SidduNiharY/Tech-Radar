"""Asking one book: reply to a Ready message, /ask as a reply, chapters list (Phase 2c Task 8).

SEC: SEC-26, SEC-37, SEC-41.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import book_ask
from techradar.bot import main as bot_main
from techradar.bot.routing import Routed, route_update
from techradar.worker.names import ASK

OWNER = 123


# --- routing -----------------------------------------------------------------------


def test_plain_reply_to_a_ready_message_is_a_book_question() -> None:
    res = route_update(OWNER, "What is CRR?", OWNER, reply_to_message_id=7, ready_message_ids={7})
    assert res == Routed("ask_book", "What is CRR?")


def test_plain_reply_to_something_else_is_ignored() -> None:
    assert route_update(
        OWNER, "What is CRR?", OWNER, reply_to_message_id=8, ready_message_ids={7}
    ) == Routed("ignore")
    assert route_update(OWNER, "What is CRR?", OWNER) == Routed("ignore")


def test_stranger_or_group_reply_is_never_a_book_question() -> None:
    for chat in (7, -100):
        res = route_update(chat, "q?", OWNER, {-100}, reply_to_message_id=7, ready_message_ids={7})
        assert res == Routed("ignore")


def test_unknown_command_reply_is_ignored_and_ask_stays_ask() -> None:
    kw = {"reply_to_message_id": 7, "ready_message_ids": {7}}
    assert route_update(OWNER, "/help me", OWNER, **kw) == Routed("ignore")
    assert route_update(OWNER, "/ask what is CRR", OWNER, **kw) == Routed("ask", "what is CRR")


# --- reply lookup and the bot handler ------------------------------------------------


def test_reply_message_id_accepts_only_real_ints() -> None:
    assert book_ask.reply_message_id(SimpleNamespace(reply_to_message=None)) is None
    assert book_ask.reply_message_id(SimpleNamespace()) is None
    assert book_ask.reply_message_id(SimpleNamespace(reply_to_message=MagicMock())) is None
    assert (
        book_ask.reply_message_id(SimpleNamespace(reply_to_message=SimpleNamespace(message_id=9)))
        == 9
    )
    assert (
        book_ask.reply_message_id(
            SimpleNamespace(reply_to_message=SimpleNamespace(message_id=True))
        )
        is None
    )


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(telegram_owner_chat_id=OWNER, max_question_chars=500)
    monkeypatch.setattr(bot_main, "get_settings", lambda: settings)
    # Phase 3: the reply-target lookup (briefing "My take") has its own tests; here a reply
    # points at nothing special, so it stays an ordinary reply.
    monkeypatch.setattr(bot_main, "find_reply_target", AsyncMock(return_value=None))


def _update(chat_id: int, text: str, reply_to: int | None = None):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.reply_to_message = (
        SimpleNamespace(message_id=reply_to) if reply_to is not None else None
    )
    session = MagicMock()

    @asynccontextmanager
    async def factory():
        yield session

    task = MagicMock()
    task.defer_async = AsyncMock()
    proc = MagicMock()
    proc.configure_task.return_value = task
    context = MagicMock()
    context.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": factory,
        "procrastinate_app": proc,
    }
    return update, context, task, proc


@pytest.fixture
def lookup(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=77)
    monkeypatch.setattr(book_ask, "ready_doc_for_reply", mock)
    return mock


async def test_reply_to_a_ready_message_asks_that_book(lookup) -> None:
    update, context, task, proc = _update(OWNER, "What is CRR?", reply_to=5)
    await bot_main.handle_message(update, context)
    lookup.assert_awaited_once()
    assert lookup.await_args.args[1:] == (OWNER, 5)
    proc.configure_task.assert_called_once_with(name=ASK)
    task.defer_async.assert_awaited_once_with(chat_id=OWNER, question="What is CRR?", doc_id=77)


async def test_ask_command_as_a_reply_asks_that_book(lookup) -> None:
    update, context, task, _proc = _update(OWNER, "/ask What is CRR?", reply_to=5)
    await bot_main.handle_message(update, context)
    task.defer_async.assert_awaited_once_with(chat_id=OWNER, question="What is CRR?", doc_id=77)


async def test_ask_command_as_a_reply_to_something_else_is_a_normal_ask(lookup) -> None:
    lookup.return_value = None
    update, context, task, _proc = _update(OWNER, "/ask What is CRR?", reply_to=5)
    await bot_main.handle_message(update, context)
    task.defer_async.assert_awaited_once_with(chat_id=OWNER, question="What is CRR?")


async def test_plain_reply_to_something_else_gets_no_answer(lookup) -> None:
    lookup.return_value = None
    update, context, task, _proc = _update(OWNER, "What is CRR?", reply_to=5)
    await bot_main.handle_message(update, context)
    task.defer_async.assert_not_called()
    update.message.reply_text.assert_not_called()


async def test_plain_text_without_a_reply_is_ignored_without_a_lookup(lookup) -> None:
    update, context, task, _proc = _update(OWNER, "What is CRR?")
    await bot_main.handle_message(update, context)
    assert lookup.await_count == 0
    task.defer_async.assert_not_called()


async def test_stranger_reply_gets_nothing_and_no_lookup(lookup) -> None:
    update, context, task, _proc = _update(999, "What is CRR?", reply_to=5)
    await bot_main.handle_message(update, context)
    assert lookup.await_count == 0
    task.defer_async.assert_not_called()
    update.message.reply_text.assert_not_called()


async def test_group_ask_as_a_reply_never_looks_up_a_book(monkeypatch, lookup) -> None:
    from techradar.bot import routing

    real = routing.route_update
    seen: dict[str, object] = {}

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)

    monkeypatch.setattr(bot_main, "route_update", spy)
    settings = SimpleNamespace(telegram_owner_chat_id=OWNER, max_question_chars=500)
    monkeypatch.setattr(bot_main, "get_settings", lambda: settings)
    update, context, _task, _proc = _update(-100, "/ask q", reply_to=5)
    await bot_main.handle_message(update, context)
    assert lookup.await_count == 0
    assert not seen.get("ready_message_ids")


async def test_overlong_question_is_refused_before_any_job(lookup) -> None:
    update, context, task, _proc = _update(OWNER, "x" * 501, reply_to=5)
    await bot_main.handle_message(update, context)
    task.defer_async.assert_not_called()
    (text,), _ = update.message.reply_text.call_args
    assert "500" in text


async def test_reply_without_a_database_is_not_a_book_ask(lookup) -> None:
    update, context, task, _proc = _update(OWNER, "What is CRR?", reply_to=5)
    del context.application.bot_data["session_factory"]
    await bot_main.handle_message(update, context)
    assert lookup.await_count == 0
    task.defer_async.assert_not_called()


async def test_plain_ask_still_works_and_empty_ask_gets_usage() -> None:
    update, context, task, _proc = _update(OWNER, "/ask what is repo rate?")
    await bot_main.handle_message(update, context)
    task.defer_async.assert_awaited_once_with(chat_id=OWNER, question="what is repo rate?")
    update.message.reply_text.assert_awaited_once_with("Thinking...")
    update, context, task, _proc = _update(OWNER, "/ask")
    await bot_main.handle_message(update, context)
    task.defer_async.assert_not_called()


# --- the Chapters button (`chap:<doc_id>`) --------------------------------------------


def _chap_query(data: str, *, user: int = OWNER, chat: int | None = OWNER):
    from telegram import Update

    query = MagicMock()
    query.data = data
    query.from_user.id = user
    query.answer = AsyncMock()
    query.message = MagicMock() if chat is not None else None
    if chat is not None:
        query.message.chat.id = chat
        query.message.reply_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.callback_query = query
    session = MagicMock()

    @asynccontextmanager
    async def factory():
        yield session

    context = MagicMock()
    context.application.bot_data = {"owner_id": OWNER, "session_factory": factory}
    return update, context, query, session


async def test_owner_chapters_button_lists_the_chapters(monkeypatch) -> None:
    from techradar.bot import callbacks

    listing = AsyncMock(return_value="Book · 2 chapters\n1. Money (pp. 1-9)")
    monkeypatch.setattr(callbacks, "chapters_listing", listing)
    update, context, query, session = _chap_query("chap:7")
    await callbacks.handle_callback_query(update, context)
    listing.assert_awaited_once_with(session, 7)
    query.message.reply_text.assert_awaited_once_with("Book · 2 chapters\n1. Money (pp. 1-9)")
    query.answer.assert_awaited_once_with()


@pytest.mark.parametrize(
    "data", ["chap", "chap:", "chap:x", "chap:-1", "chap:1:2", "chap:0", "chap:1000000000000"]
)
async def test_chapters_button_rejects_bad_data(monkeypatch, data) -> None:
    from techradar.bot import callbacks

    listing = AsyncMock()
    monkeypatch.setattr(callbacks, "chapters_listing", listing)
    update, context, query, _session = _chap_query(data)
    await callbacks.handle_callback_query(update, context)
    assert listing.await_count == 0
    query.message.reply_text.assert_not_called()


async def test_chapters_button_from_a_stranger_does_nothing(monkeypatch) -> None:
    from techradar.bot import callbacks

    listing = AsyncMock()
    monkeypatch.setattr(callbacks, "chapters_listing", listing)
    update, context, query, _session = _chap_query("chap:7", user=999)
    await callbacks.handle_callback_query(update, context)
    assert listing.await_count == 0
    query.message.reply_text.assert_not_called()


async def test_chapters_button_outside_the_owner_chat_does_nothing(monkeypatch) -> None:
    from techradar.bot import callbacks

    listing = AsyncMock()
    monkeypatch.setattr(callbacks, "chapters_listing", listing)
    for chat in (-100, None):
        update, context, query, _session = _chap_query("chap:7", chat=chat)
        await callbacks.handle_callback_query(update, context)
        assert listing.await_count == 0
        query.answer.assert_awaited_once_with("Not available.")


async def test_chapters_of_a_book_that_is_not_ready_say_so(monkeypatch) -> None:
    from techradar.bot import callbacks

    monkeypatch.setattr(callbacks, "chapters_listing", AsyncMock(return_value=None))
    update, context, query, _session = _chap_query("chap:7")
    await callbacks.handle_callback_query(update, context)
    query.message.reply_text.assert_not_called()
    query.answer.assert_awaited_once_with("Nothing to show.")


async def test_chapters_button_without_a_database(monkeypatch) -> None:
    from techradar.bot import callbacks

    update, context, query, _session = _chap_query("chap:7")
    del context.application.bot_data["session_factory"]
    await callbacks.handle_callback_query(update, context)
    query.answer.assert_awaited_once_with("Not available yet.")


# --- the listing text -----------------------------------------------------------------


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    scalar_one = scalar_one_or_none

    def scalars(self):
        return self

    def all(self):
        return self.value


def _chapter(ordinal, title, **kw):
    base = {"page_start": None, "page_end": None, "ts_start": None, "ts_end": None}
    return SimpleNamespace(ordinal=ordinal, title=title, **{**base, **kw})


def _session(title, chapters):
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[_Result(title), _Result(len(chapters)), _Result(chapters)]
    )
    return session


async def test_listing_shows_title_pages_and_clean_titles() -> None:
    session = _session(
        "Indian\x00 Economy",
        [
            _chapter(0, "Money\nand  banking", page_start=1, page_end=9),
            _chapter(1, "One page", page_start=10, page_end=10),
            _chapter(2, "Lecture", ts_start=65, ts_end=3725),
            _chapter(3, "No range"),
        ],
    )
    text = await book_ask.chapters_listing(session, 7)
    assert text.splitlines() == [
        "Indian Economy · 4 chapters",
        "1. Money and banking (pp. 1-9)",
        "2. One page (p. 10)",
        "3. Lecture (1:05-1:02:05)",
        "4. No range",
        "Reply to the Ready message with a question to ask this book.",
    ]


async def test_listing_of_a_missing_or_unready_book_is_none() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_Result(None)])
    assert await book_ask.chapters_listing(session, 7) is None
    assert await book_ask.chapters_listing(session, 0) is None
    assert await book_ask.chapters_listing(session, True) is None  # type: ignore[arg-type]


async def test_listing_stays_inside_a_telegram_message() -> None:
    chapters = [_chapter(i, "T" * 300, page_start=i, page_end=i + 1) for i in range(60)]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_Result("B"), _Result(200), _Result(chapters)])
    text = await book_ask.chapters_listing(session, 7)
    assert len(text) < 4096
    assert "more." in text
    assert text.count("\n1.") == 1


# --- the reply lookup query -------------------------------------------------------------


async def test_lookup_query_is_owner_scoped_sent_and_ready_only() -> None:
    captured = []

    class S:
        async def execute(self, stmt):
            captured.append(stmt)
            return _Result(9)

    assert await book_ask.ready_doc_for_reply(S(), OWNER, 5) == 9  # type: ignore[arg-type]
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
    assert f"outbox.chat_id = {OWNER}" in sql
    assert "outbox.purpose = 'library_ready'" in sql
    assert "outbox.sent_message_id = 5" in sql
    assert "outbox.sent_at IS NOT NULL" in sql
    assert "library_docs.status = 'ready'" in sql


async def test_lookup_rejects_bad_ids_without_a_query() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    for bad in (0, -1, True, "5", 10**12):
        assert await book_ask.ready_doc_for_reply(session, OWNER, bad) is None  # type: ignore[arg-type]
    assert session.execute.await_count == 0

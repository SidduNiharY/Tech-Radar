"""Owner-only Telegram bot application (Phase 2b Task 6).

SEC: SEC-26, SEC-37, SEC-39, SEC-41.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from telegram import (
    Audio,
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    VideoNote,
    Voice,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from techradar.bot.book_ask import find_ready_doc, handle_ask, reply_message_id
from techradar.bot.callbacks import handle_callback_query
from techradar.bot.drill import start_drill
from techradar.bot.econ import handle_econ
from techradar.bot.intake import (
    NOT_SAVED_REPLY,
    handle_document,
    handle_link,
    handle_paste,
    is_owner_message,
)
from techradar.bot.packs_command import packs_reply
from techradar.bot.planner_commands import handle_planner_command
from techradar.bot.practice_commands import COMMAND_JOBS, handle_inbox, handle_practice_command
from techradar.bot.predict import find_prediction, handle_predict, handle_prediction_reply
from techradar.bot.render import START_TEXT, render_status
from techradar.bot.reply_target import find_reply_target
from techradar.bot.routing import route_update
from techradar.bot.take_reply import handle_take
from techradar.bot.voice_intake import handle_voice
from techradar.db.engine import make_session_factory
from techradar.library.quarantine import quarantine_listing
from techradar.logs import configure_logging
from techradar.messaging.outbox import send_pending
from techradar.ops.status import (
    check_db_live,
    check_disk_live,
    check_ollama_live,
    collect_status,
)
from techradar.settings import get_settings, read_secret
from techradar.voice.intake import NOT_VOICE_REPLY

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and dispatch to routed handler."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    text = update.message.text
    settings = get_settings()

    # --- Phase 3 Task 3: a document is checked before any download, owner only (SEC-26) ---
    if isinstance(getattr(update.message, "document", None), Document):
        if not is_owner_message(update, settings.telegram_owner_chat_id):
            logger.warning("ignored a file from chat %s", chat_id)
            return
        try:
            await handle_document(update, context)
        except Exception:
            logger.exception("could not take a document from the owner")
            await update.message.reply_text(NOT_SAVED_REPLY)
        return

    # --- Phase 6 Task 1: a voice note is checked before any download, owner only (SEC-26) ---
    message = update.message
    if isinstance(getattr(message, "voice", None), Voice):
        if not is_owner_message(update, settings.telegram_owner_chat_id):
            logger.warning("ignored a voice note from chat %s", chat_id)
            return
        try:
            await handle_voice(update, context)
        except Exception:
            logger.exception("could not take a voice note from the owner")
            await message.reply_text(NOT_SAVED_REPLY)
        return
    if isinstance(getattr(message, "audio", None), Audio) or isinstance(
        getattr(message, "video_note", None), VideoNote
    ):  # only voice notes are analysed; nothing else is downloaded
        if is_owner_message(update, settings.telegram_owner_chat_id):
            await message.reply_text(NOT_VOICE_REPLY)
        return

    # A reply to a Ready message asks that book. Only the owner's own chat is looked up, and
    # a database failure never silently widens the question to every note.
    reply_id = reply_message_id(update.message)
    ready_doc: int | None = None
    if reply_id is not None and chat_id == settings.telegram_owner_chat_id:
        try:
            ready_doc = await find_ready_doc(context.application.bot_data, chat_id, reply_id)
        except Exception:
            logger.exception("could not look up the Ready message")
            await update.message.reply_text("Not available yet.")
            return

    # --- Phase 3: what the reply points at; a sent briefing message makes it a "My take" ---
    reply_purpose: str | None = None
    reply_ref: int | None = None
    if reply_id is not None and chat_id == settings.telegram_owner_chat_id and ready_doc is None:
        try:
            target = await find_reply_target(context.application.bot_data, chat_id, reply_id)
        except Exception:
            logger.exception("could not look up the replied-to message")
            await update.message.reply_text("Not available yet.")
            return
        if target is not None:
            reply_purpose, reply_ref = target

    # --- Phase 7: a reply to a prediction reminder (the owner's own chat only) ---
    prediction_id: int | None = None
    if reply_id is not None and chat_id == settings.telegram_owner_chat_id:
        try:
            prediction_id = await find_prediction(context.application.bot_data, chat_id, reply_id)
        except Exception:
            logger.exception("could not look up the prediction reminder")

    routed = route_update(
        chat_id=chat_id,
        text=text,
        owner_id=settings.telegram_owner_chat_id,
        reply_to_message_id=reply_id,
        ready_message_ids=frozenset({reply_id}) if ready_doc and reply_id else frozenset(),
        reply_to_purpose=reply_purpose,
        reply_to_ref=reply_ref,
        prediction_message_ids=(
            frozenset({reply_id}) if prediction_id and reply_id else frozenset()
        ),
    )

    if routed.action == "ignore":
        if chat_id != settings.telegram_owner_chat_id:
            logger.warning("ignored update from chat %s", chat_id)
        return

    if routed.action == "start":
        await update.message.reply_text(START_TEXT)
        return

    if routed.action == "status":
        status = await collect_status(
            check_db=check_db_live,
            check_ollama=check_ollama_live,
            check_disk=check_disk_live,
        )
        reply = render_status(status)
        await update.message.reply_text(reply)
        return

    # --- Phase 8 ---
    if routed.action == "drill":  # the router allows it from the owner's own chat only
        await start_drill(update, context.application.bot_data, settings.tz)
        return
    # --- end Phase 8 ---

    if routed.action == "quarantine":  # the router allows it from the owner's own chat only
        session_factory = context.application.bot_data.get("session_factory")
        if session_factory is None:
            await update.message.reply_text("Not available yet.")
            return
        async with session_factory() as session:
            text, buttons = await quarantine_listing(session)
        markup = (
            InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(b.text, callback_data=b.data) for b in row]
                    for row in buttons
                ]
            )
            if buttons
            else None
        )
        await update.message.reply_text(text, reply_markup=markup)
        return

    if routed.action == "packs":  # the router allows it from the owner's own chat only
        bot_data = context.application.bot_data
        owner = settings.telegram_owner_chat_id
        reply = await packs_reply(chat_id, owner, bot_data.get("session_factory"))
        if reply is not None:
            await update.message.reply_text(reply)
        return

    # --- Phase 5 ---
    if routed.action in ("study", "stop", "skill"):  # the router allows the owner's chat only
        try:
            reply = await handle_planner_command(
                routed.action, routed.arg, context.application.bot_data
            )
        except Exception:
            logger.exception("planner command failed")
            reply = "Not available yet."
        await update.message.reply_text(reply)
        return

    if routed.action == "inbox":  # --- Phase 3: the review inbox (owner's chat only) ---
        await handle_inbox(update, context.application.bot_data)
        return

    if routed.action in COMMAND_JOBS:  # --- Phase 3: /quiz and /cards queue a job by name ---
        await handle_practice_command(update, context.application.bot_data, routed.action)
        return

    if routed.action == "take" and reply_ref is not None:  # --- Phase 3 ---
        await handle_take(update, context.application.bot_data, routed.arg, reply_ref)
        return

    # --- Phase 7: the router allows both from the owner's own chat only ---
    if routed.action == "econ":
        await handle_econ(update, context.application.bot_data, routed.arg)
        return

    if routed.action == "predict":
        today = datetime.now(ZoneInfo(settings.tz)).date()
        await handle_predict(update, context.application.bot_data, routed.arg, today=today)
        return

    if routed.action == "prediction_reply" and prediction_id is not None:
        await handle_prediction_reply(
            update, context.application.bot_data, prediction_id, routed.arg
        )
        return

    # --- Phase 3 Task 3: the router allows both from the owner's own chat only ---
    if routed.action in ("link", "paste"):
        if not is_owner_message(update, settings.telegram_owner_chat_id):
            return
        if routed.action == "link":
            await handle_link(update, context.application.bot_data, routed.arg)
        else:
            await handle_paste(update, context.application.bot_data, routed.arg)
        return

    if routed.action in ("ask", "ask_book"):
        await handle_ask(
            update,
            context.application.bot_data,
            routed.arg,
            doc_id=ready_doc,
            max_chars=settings.max_question_chars,
        )


async def outbox_worker(app_bot: Any, session_factory: Any) -> None:
    """Periodically drain and send pending outbox messages."""
    while True:
        try:
            await send_pending(app_bot, session_factory)
        except Exception as exc:
            logger.warning("Error in outbox worker: %s", exc)
        await asyncio.sleep(5.0)


async def post_init(application: Application) -> None:
    """Initialize bot dependencies and launch outbox background loop."""
    settings = get_settings()
    session_factory = make_session_factory("app", settings)
    application.bot_data["owner_id"] = settings.telegram_owner_chat_id
    application.bot_data["tz"] = settings.tz  # Phase 3: "today" for quiz answers is local
    # /quarantine and its buttons (bot/callbacks.py). No release gate: the bot never runs
    # the Intake Gateway; released library docs are re-gated in the parser sandbox.
    application.bot_data["session_factory"] = session_factory
    # The bot mounts only data/quarantine (rw, to delete held copies); worker-bulk deletes
    # the originals of deleted held library docs, so the bot never writes the library.
    application.bot_data["quarantine_dir"] = settings.data_dir / "quarantine"
    # --- Phase 5 --- (/skill edits skills/<name>.md; the vault must be writable in `bot`)
    application.bot_data["vault_root"] = settings.data_dir / "vault"
    application.bot_data["tz"] = settings.tz  # Phase 8: the day a drill question belongs to
    # --- Phase 3 Task 3: the bot's private drop folder for owner PDFs and pasted notes. The
    # worker's owner_file job moves them into raw/; the bot never mounts raw/ or parse-jobs/.
    application.bot_data["owner_in_dir"] = settings.data_dir / "telegram-in"
    # --- Phase 6 Task 1: voice notes are saved in data/voice/in (the bot's only voice mount)
    application.bot_data["voice_dir"] = settings.data_dir / "voice"

    try:
        from procrastinate import App, PsycopgConnector

        try:
            pw = read_secret("tr_app_password", settings.secrets_dir)
        except Exception:
            pw = ""

        connector = PsycopgConnector(
            kwargs={
                "host": settings.db_host,
                "port": settings.db_port,
                "dbname": settings.db_name,
                "user": "tr_app",
                "password": pw,
            }
        )
        proc_app = App(connector=connector)
        application.bot_data["procrastinate_app"] = proc_app
    except Exception as exc:
        logger.warning("Failed to initialize procrastinate in bot: %s", exc)

    asyncio.create_task(outbox_worker(application.bot, session_factory))


def main() -> None:
    """Entry point for the Telegram bot daemon."""
    settings = get_settings()
    token = read_secret("telegram_bot_token", settings.secrets_dir)
    configure_logging(secrets=[token])

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info("Starting Telegram bot for owner %s...", settings.telegram_owner_chat_id)
    app.run_polling()


if __name__ == "__main__":
    main()

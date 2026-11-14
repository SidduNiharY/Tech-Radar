"""Owner-only Telegram bot application (Phase 2b Task 6).

SEC: SEC-26, SEC-37, SEC-39, SEC-41.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from techradar.bot.callbacks import handle_callback_query
from techradar.bot.render import START_TEXT, render_status
from techradar.bot.routing import route_update
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
from techradar.worker.names import ASK

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and dispatch to routed handler."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    text = update.message.text
    settings = get_settings()

    routed = route_update(
        chat_id=chat_id,
        text=text,
        owner_id=settings.telegram_owner_chat_id,
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

    if routed.action == "ask":
        if not routed.arg:
            await update.message.reply_text(
                "Please provide a question, e.g. /ask what is repo rate?"
            )
            return

        procrastinate_app = context.application.bot_data.get("procrastinate_app")
        if procrastinate_app:
            await procrastinate_app.configure_task(name=ASK).defer_async(
                chat_id=chat_id,
                question=routed.arg,
            )
        await update.message.reply_text("Thinking...")


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
    # /quarantine and its buttons (bot/callbacks.py). No release gate: the bot never runs
    # the Intake Gateway; released library docs are re-gated in the parser sandbox.
    application.bot_data["session_factory"] = session_factory
    application.bot_data["quarantine_dir"] = settings.data_dir / "quarantine"

    try:
        from procrastinate import App, PsycopgConnector

        try:
            pw = read_secret("tr_app_password", settings.secrets_dir)
        except Exception:
            pw = ""

        connector = PsycopgConnector(
            host=settings.db_host,
            port=settings.db_port,
            user="tr_app",
            password=pw,
            database=settings.db_name,
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

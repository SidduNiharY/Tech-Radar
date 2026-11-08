"""Owner-only Telegram bot application."""

import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from techradar.bot.render import START_TEXT, render_status
from techradar.bot.routing import route_update
from techradar.logs import configure_logging
from techradar.ops.status import (
    check_db_live,
    check_disk_live,
    check_ollama_live,
    collect_status,
)
from techradar.settings import get_settings, read_secret

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and dispatch to routed handler."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    text = update.message.text
    settings = get_settings()

    action = route_update(
        chat_id=chat_id,
        text=text,
        owner_id=settings.telegram_owner_chat_id,
    )

    if action == "ignore":
        if chat_id != settings.telegram_owner_chat_id:
            logger.warning("ignored update from chat %s", chat_id)
        return

    if action == "start":
        await update.message.reply_text(START_TEXT)
        return

    if action == "status":
        status = await collect_status(
            check_db=check_db_live,
            check_ollama=check_ollama_live,
            check_disk=check_disk_live,
        )
        reply = render_status(status)
        await update.message.reply_text(reply)


def main() -> None:
    """Entry point for the Telegram bot daemon."""
    settings = get_settings()
    token = read_secret("telegram_bot_token", settings.secrets_dir)
    configure_logging(secrets=[token])

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE, handle_message))

    logger.info("Starting Telegram bot for owner %s...", settings.telegram_owner_chat_id)
    app.run_polling()


if __name__ == "__main__":
    main()

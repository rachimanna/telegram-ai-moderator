import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.db.session import SessionLocal
from app.services.moderation import moderate_message

logger = logging.getLogger(__name__)


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or chat is None or user is None:
        return

    if chat.type not in {
        "group",
        "supergroup",
    }:
        return

    text = message.text or message.caption or ""

    if not text.strip():
        return

    username = user.username or ""
    display_name = user.full_name or username or "Пользователь"

    chat_title = (
        chat.title
        or "Без названия"
    )

    try:
        async with SessionLocal() as session:
            action = await moderate_message(
                session=session,
                context=context,
                chat_id=chat.id,
                chat_title=chat_title,
                user_id=user.id,
                username=username,
                display_name=display_name,
                telegram_message_id=message.message_id,
                text=text,
            )

            logger.info(
                "Message processed: "
                "chat=%s user=%s message=%s action=%s",
                chat.id,
                user.id,
                message.message_id,
                action,
            )

    except Exception:
        logger.exception(
            "Failed to process incoming message: "
            "chat=%s user=%s message=%s",
            chat.id,
            user.id,
            message.message_id,
        )


def register_message_handlers(
    application,
) -> None:
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & (
                filters.TEXT
                | filters.CaptionRegex(r".+")
            )
            & ~filters.COMMAND,
            handle_message,
        )
    )

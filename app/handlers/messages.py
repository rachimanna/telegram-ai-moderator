import logging
import re

from sqlalchemy import select
from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import get_settings
from app.db.models import Group
from app.db.session import SessionLocal
from app.services.assistant import answer_question
from app.services.moderation import moderate_message
from app.services.settings import get_or_create_settings

logger = logging.getLogger(__name__)


def get_message_text(update: Update) -> str:
    message = update.effective_message

    if message is None:
        return ""

    if message.text:
        return message.text.strip()

    if message.caption:
        return message.caption.strip()

    return ""


def is_bot_mentioned(
    update: Update,
    bot_username: str | None,
) -> bool:
    if not bot_username:
        return False

    text = get_message_text(update)

    if not text:
        return False

    username = bot_username.lstrip("@").lower()

    pattern = rf"@{re.escape(username)}\b"

    return re.search(
        pattern,
        text.lower(),
    ) is not None


def remove_bot_mention(
    text: str,
    bot_username: str | None,
) -> str:
    if not bot_username:
        return text.strip()

    username = bot_username.lstrip("@")

    pattern = rf"@{re.escape(username)}\b"

    cleaned = re.sub(
        pattern,
        "",
        text,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


async def get_group_by_telegram_id(
    chat_id: int,
):
    async with SessionLocal() as session:
        result = await session.execute(
            select(Group).where(
                Group.telegram_id == chat_id
            )
        )

        return result.scalar_one_or_none()


async def handle_group_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None:
        return

    if chat is None:
        return

    if user is None:
        return

    if chat.type not in {
        "group",
        "supergroup",
    }:
        return

    text = get_message_text(update)

    if not text:
        return

    settings = get_settings()

    if len(text) > settings.max_message_length:
        text = text[:settings.max_message_length]

    # -----------------------------------------------------
    # Get bot username
    # -----------------------------------------------------

    bot_username = None

    try:
        me = await context.bot.get_me()
        bot_username = me.username

    except Exception:
        logger.exception(
            "Failed to get bot information."
        )

    mentioned = is_bot_mentioned(
        update,
        bot_username,
    )

    username = (
        f"@{user.username}"
        if user.username
        else user.full_name
    )

    # -----------------------------------------------------
    # AI assistant
    # -----------------------------------------------------

    if mentioned:
        question = remove_bot_mention(
            text,
            bot_username,
        )

        if question:
            try:
                async with SessionLocal() as session:
                    result = await session.execute(
                        select(Group).where(
                            Group.telegram_id == chat.id
                        )
                    )

                    group = (
                        result.scalar_one_or_none()
                    )

                    if group is not None:
                        group_settings = (
                            await get_or_create_settings(
                                session,
                                group,
                            )
                        )

                        if group_settings.ai_answers_enabled:
                            answer = await answer_question(
                                session,
                                group.id,
                                question,
                            )

                            await session.commit()

                            await message.reply_text(
                                answer,
                                disable_web_page_preview=True,
                            )

                            return

            except Exception:
                logger.exception(
                    "AI assistant failed."
                )

                try:
                    await message.reply_text(
                        "⚠️ Не удалось обработать "
                        "запрос. Попробуйте позже."
                    )

                except Exception:
                    logger.exception(
                        "Failed to send AI error message."
                    )

                return

    # -----------------------------------------------------
    # Moderation
    # -----------------------------------------------------

    try:
        async with SessionLocal() as session:
            action = await moderate_message(
                session,
                context,
                chat_id=chat.id,
                chat_title=chat.title or "Telegram Group",
                user_id=user.id,
                username=username,
                telegram_message_id=message.message_id,
                text=text,
            )

            logger.info(
                "Message processed: "
                "chat=%s user=%s action=%s",
                chat.id,
                user.id,
                action,
            )

    except Exception:
        logger.exception(
            "Failed to process group message."
        )


def register_message_handlers(
    application,
) -> None:
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & filters.TEXT
            & ~filters.COMMAND,
            handle_group_message,
        )
    )

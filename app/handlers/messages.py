import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.db.session import SessionLocal
from app.services.assistant import answer_question
from app.services.moderation import moderate_message
from app.services.settings import (
    get_or_create_group,
    get_or_create_settings,
)

logger = logging.getLogger(__name__)


def extract_question(
    text: str,
    bot_username: str | None,
) -> str | None:
    """
    Return the question text if the message mentions the bot,
    otherwise None.
    """

    stripped = text.strip()

    if not stripped:
        return None

    if not bot_username:
        return None

    mention = f"@{bot_username}".lower()

    lowered = stripped.lower()

    index = lowered.find(mention)

    if index == -1:
        return None

    question = (
        stripped[:index]
        + stripped[index + len(mention):]
    ).strip()

    return question or None


async def answer_bot_mention(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    question: str,
) -> None:
    try:
        async with SessionLocal() as session:
            try:
                group = await get_or_create_group(
                    session,
                    telegram_group_id=chat_id,
                    title="Telegram Group",
                )

                settings = await get_or_create_settings(
                    session,
                    group,
                )

                if not settings.ai_answers_enabled:
                    await session.commit()

                    return

                answer = await answer_question(
                    session,
                    group.id,
                    question,
                )

                await session.commit()

            except Exception as db_error:
                logger.error(
                    f"Database error in answer_bot_mention: {db_error}",
                    exc_info=True,
                )
                await session.rollback()
                raise

        await context.bot.send_message(
            chat_id=chat_id,
            text=answer,
            reply_to_message_id=message_id,
        )

    except Exception:
        logger.exception(
            "Failed to answer bot mention: "
            "chat=%s message=%s",
            chat_id,
            message_id,
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message

    if message is None:
        return

    chat = update.effective_chat

    if chat is None:
        return

    user = update.effective_user

    if user is None:
        return

    text = (
        message.text
        or message.caption
        or ""
    )

    if not text:
        return

    if len(text) > 4000:
        text = text[:4000]

    try:
        async with SessionLocal() as session:
            try:
                action = await moderate_message(
                    session=session,
                    context=context,
                    chat_id=chat.id,
                    chat_title=chat.title or "Telegram Group",
                    user_id=user.id,
                    username=user.username or "",
                    display_name=(
                        user.first_name
                        + (
                            f" {user.last_name}"
                            if user.last_name
                            else ""
                        )
                    ),
                    telegram_message_id=message.message_id,
                    text=text,
                )

            except Exception as mod_error:
                logger.error(
                    f"Moderation error: {mod_error}",
                    exc_info=True,
                )
                await session.rollback()
                action = "allowed"

    except Exception:
        logger.exception(
            "Failed to process incoming message: "
            "chat=%s user=%s message=%s",
            chat.id,
            user.id,
            message.message_id,
        )

        return

    if action in {"delete", "restrict"}:
        return

    bot_username = (
        context.bot.username
        if context.bot is not None
        else None
    )

    question = extract_question(
        text,
        bot_username,
    )

    if question is None:
        return

    await answer_bot_mention(
        context,
        chat.id,
        message.message_id,
        question,
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

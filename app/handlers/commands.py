import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
)

from app.db.models import Group
from app.db.session import SessionLocal
from app.services.assistant import answer_today_question


logger = logging.getLogger(__name__)


async def get_group(
    session,
    chat_id: int,
) -> Group | None:
    result = await session.execute(
        select(Group).where(
            Group.telegram_id == chat_id
        )
    )

    return result.scalar_one_or_none()


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message

    if message is None:
        logger.warning(
            "Received /start without effective message."
        )
        return

    logger.info(
        "Processing /start from user_id=%s chat_id=%s",
        update.effective_user.id
        if update.effective_user
        else None,
        update.effective_chat.id
        if update.effective_chat
        else None,
    )

    await message.reply_text(
        "👋 Привет!\n\n"
        "Я AI-модератор и помощник группы.\n\n"
        "Я умею:\n"
        "• обнаруживать спам и флуд;\n"
        "• выдавать предупреждения;\n"
        "• удалять нарушения;\n"
        "• временно ограничивать нарушителей;\n"
        "• отвечать на вопросы по истории группы;\n"
        "• делать сводки обсуждений;\n"
        "• показывать статистику.\n\n"
        "Используйте /help для списка команд."
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message

    if message is None:
        return

    await message.reply_text(
        "📖 Команды AI-модератора\n\n"
        "Основные:\n"
        "/start — запуск бота\n"
        "/help — список команд\n\n"
        "🤖 AI:\n"
        "/today — что обсуждали сегодня\n"
        "@бот ваш вопрос — задать вопрос по истории группы\n\n"
        "📊 Статистика:\n"
        "/stats — общая статистика\n"
        "/top — самые активные участники\n"
        "/activity — активность за неделю\n"
        "/moderation — журнал модерации\n\n"
        "⚙️ Администратор:\n"
        "/settings — настройки AI-модерации\n"
        "/mute — замьютить (ответом на сообщение, "
        "по умолчанию 10 мин, можно /mute 30)\n"
        "/unmute — снять мут (ответом на сообщение)\n\n"
        "Пример:\n"
        "@бот кто предложил эту идею?"
    )


async def today_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    if chat.type not in {
        "group",
        "supergroup",
    }:
        await message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    question = (
        "Сделай краткий обзор того, "
        "что сегодня обсуждали."
    )

    async with SessionLocal() as session:
        group = await get_group(
            session,
            chat.id,
        )

        if group is None:
            await message.reply_text(
                "Сегодня ещё нет сохранённой истории."
            )
            return

        try:
            answer = await answer_today_question(
                session,
                group.id,
                question,
            )

            await session.commit()

        except Exception:
            await session.rollback()

            logger.exception(
                "Today's summary command failed."
            )

            await message.reply_text(
                "⚠️ Не удалось создать сводку. "
                "Попробуйте позже."
            )

            return

    await message.reply_text(
        "📋 Что обсуждали сегодня:\n\n"
        f"{answer}"
    )


async def unknown_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message

    if message is None:
        return

    await message.reply_text(
        "❓ Неизвестная команда.\n\n"
        "Используйте /help, чтобы увидеть "
        "список доступных команд."
    )


def register_command_handlers(
    application,
) -> None:
    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "today",
            today_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "unknown",
            unknown_command,
        )
    )

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
)

from app.db.models import (
    Group,
    Message,
    ModerationLog,
    User,
)
from app.db.session import SessionLocal
from app.services.analytics import get_statistics
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
    if update.effective_message is None:
        return

    await update.effective_message.reply_text(
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
    if update.effective_message is None:
        return

    await update.effective_message.reply_text(
        "📖 Команды бота\n\n"
        "/start — запуск\n"
        "/help — помощь\n"
        "/stats — статистика группы\n"
        "/activity — активность за 7 дней\n"
        "/top — самые активные участники\n"
        "/moderation — статистика модерации\n"
        "/today — что обсуждали сегодня\n\n"
        "Также можно написать:\n"
        "@бот ваш вопрос\n\n"
        "Например:\n"
        "@бот кто предложил эту идею?"
    )


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat

    if chat is None or update.effective_message is None:
        return

    if chat.type not in {"group", "supergroup"}:
        await update.effective_message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    async with SessionLocal() as session:
        group = await get_group(
            session,
            chat.id,
        )

        if group is None:
            await update.effective_message.reply_text(
                "📊 Пока нет сохранённой статистики."
            )
            return

        statistics = await get_statistics(
            session,
            group.id,
            days=7,
        )

        if not statistics:
            await update.effective_message.reply_text(
                "📊 За последние 7 дней статистики пока нет."
            )
            return

        total_messages = sum(
            item.message_count
            for item in statistics
        )

        total_violations = sum(
            item.violations
            for item in statistics
        )

        total_deleted = sum(
            item.deleted_messages
            for item in statistics
        )

        total_questions = sum(
            item.questions
            for item in statistics
        )

        await update.effective_message.reply_text(
            "📊 Статистика за последние 7 дней\n\n"
            f"💬 Сообщений: {total_messages}\n"
            f"⚠️ Нарушений: {total_violations}\n"
            f"🗑 Удалено: {total_deleted}\n"
            f"❓ Вопросов: {total_questions}"
        )


async def activity_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat

    if chat is None or update.effective_message is None:
        return

    if chat.type not in {"group", "supergroup"}:
        await update.effective_message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    async with SessionLocal() as session:
        group = await get_group(
            session,
            chat.id,
        )

        if group is None:
            await update.effective_message.reply_text(
                "📈 Данных об активности пока нет."
            )
            return

        statistics = await get_statistics(
            session,
            group.id,
            days=7,
        )

        if not statistics:
            await update.effective_message.reply_text(
                "📈 Активности за последние 7 дней нет."
            )
            return

        lines = [
            "📈 Активность за 7 дней",
            "",
        ]

        for item in statistics:
            lines.append(
                f"{item.day}: "
                f"{item.message_count} сообщений"
            )

        await update.effective_message.reply_text(
            "\n".join(lines)
        )


async def top_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat

    if chat is None or update.effective_message is None:
        return

    if chat.type not in {"group", "supergroup"}:
        await update.effective_message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    start_time = datetime.utcnow() - timedelta(days=7)

    async with SessionLocal() as session:
        group = await get_group(
            session,
            chat.id,
        )

        if group is None:
            await update.effective_message.reply_text(
                "🏆 Пока нет данных об участниках."
            )
            return

        result = await session.execute(
            select(
                Message.user_id,
                User.display_name,
                User.username,
                func.count(Message.id).label(
                    "message_count"
                ),
            )
            .join(
                User,
                User.id == Message.user_id,
            )
            .where(
                Message.group_id == group.id,
                Message.created_at >= start_time,
                Message.is_deleted.is_(False),
            )
            .group_by(
                Message.user_id,
                User.display_name,
                User.username,
            )
            .order_by(
                func.count(Message.id).desc()
            )
            .limit(10)
        )

        rows = result.all()

        if not rows:
            await update.effective_message.reply_text(
                "🏆 За последние 7 дней сообщений пока нет."
            )
            return

        lines = [
            "🏆 Самые активные участники",
            "",
        ]

        for index, row in enumerate(
            rows,
            start=1,
        ):
            name = (
                f"@{row.username}"
                if row.username
                else row.display_name
            )

            lines.append(
                f"{index}. {name} — "
                f"{row.message_count} сообщений"
            )

        await update.effective_message.reply_text(
            "\n".join(lines)
        )


async def moderation_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat

    if chat is None or update.effective_message is None:
        return

    if chat.type not in {"group", "supergroup"}:
        await update.effective_message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    start_time = datetime.utcnow() - timedelta(days=7)

    async with SessionLocal() as session:
        group = await get_group(
            session,
            chat.id,
        )

        if group is None:
            await update.effective_message.reply_text(
                "🛡 Данных модерации пока нет."
            )
            return

        result = await session.execute(
            select(
                ModerationLog.action,
                func.count(ModerationLog.id),
            )
            .where(
                ModerationLog.group_id == group.id,
                ModerationLog.created_at >= start_time,
            )
            .group_by(
                ModerationLog.action
            )
        )

        rows = result.all()

        if not rows:
            await update.effective_message.reply_text(
                "🛡 За последние 7 дней нарушений не обнаружено."
            )
            return

        lines = [
            "🛡 Модерация за 7 дней",
            "",
        ]

        for action, count in rows:
            lines.append(
                f"• {action}: {count}"
            )

        await update.effective_message.reply_text(
            "\n".join(lines)
        )


async def today_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat

    if chat is None or update.effective_message is None:
        return

    if chat.type not in {"group", "supergroup"}:
        await update.effective_message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    question = "Сделай краткий обзор того, что сегодня обсуждали."

    async with SessionLocal() as session:
        group = await get_group(
            session,
            chat.id,
        )

        if group is None:
            await update.effective_message.reply_text(
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

            await update.effective_message.reply_text(
                "⚠️ Не удалось создать сводку. "
                "Попробуйте позже."
            )

            return

    await update.effective_message.reply_text(
        f"📋 Что обсуждали сегодня:\n\n{answer}"
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
            "stats",
            stats_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "activity",
            activity_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "top",
            top_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "moderation",
            moderation_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "today",
            today_command,
        )
    )

import logging

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
)

from app.db.models import (
    Message,
    ModerationLog,
    User,
)
from app.db.session import SessionLocal
from app.services.analytics import get_statistics


logger = logging.getLogger(__name__)


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message
    chat = update.effective_chat

    if message is None or chat is None:
        return

    async with SessionLocal() as session:

        stats = await get_statistics(
            session,
            chat.id,
            days=7,
        )

        total_messages = sum(
            item.message_count
            for item in stats
        )

        total_violations = sum(
            item.violations
            for item in stats
        )

        total_deleted = sum(
            item.deleted_messages
            for item in stats
        )

        text = (
            "📊 Статистика группы\n\n"
            f"📨 Сообщений за 7 дней: "
            f"{total_messages}\n"
            f"👥 Нарушений: "
            f"{total_violations}\n"
            f"🗑 Удалено сообщений: "
            f"{total_deleted}\n"
        )

    await message.reply_text(text)


async def top_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message
    chat = update.effective_chat

    if message is None or chat is None:
        return

    async with SessionLocal() as session:

        result = await session.execute(
            select(
                User.display_name,
                func.count(Message.id)
                .label("count"),
            )
            .join(
                Message,
                Message.user_id == User.id,
            )
            .where(
                Message.group_id.is_not(None),
            )
            .group_by(
                User.id,
            )
            .order_by(
                func.count(Message.id).desc()
            )
            .limit(10)
        )

        users = result.all()

    if not users:
        await message.reply_text(
            "📭 Пока нет статистики."
        )

        return


    text = (
        "🏆 Топ активных участников:\n\n"
    )

    for index, user in enumerate(
        users,
        start=1,
    ):
        text += (
            f"{index}. "
            f"{user.display_name} — "
            f"{user.count} сообщений\n"
        )


    await message.reply_text(text)


async def moderation_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message
    chat = update.effective_chat

    if message is None or chat is None:
        return

    async with SessionLocal() as session:

        result = await session.execute(
            select(
                func.count(
                    ModerationLog.id
                )
            )
            .where(
                ModerationLog.group_id
                .is_not(None)
            )
        )

        count = result.scalar_one() or 0


    await message.reply_text(
        "🛡 Журнал модерации\n\n"
        f"Всего действий: {count}"
    )


async def activity_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message
    chat = update.effective_chat

    if message is None or chat is None:
        return


    async with SessionLocal() as session:

        stats = await get_statistics(
            session,
            chat.id,
            days=7,
        )


    text = (
        "📈 Активность за неделю:\n\n"
    )

    for item in stats:
        text += (
            f"{item.day}: "
            f"{item.message_count} сообщений\n"
        )


    await message.reply_text(text)


def register_stats_handlers(
    application,
) -> None:

    application.add_handler(
        CommandHandler(
            "stats",
            stats_command,
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
            "activity",
            activity_command,
        )
    )

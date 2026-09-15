import logging

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


logger = logging.getLogger(__name__)


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if message is None or chat is None:
        return

    if chat.type not in {
        "group",
        "supergroup",
    }:
        await message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Group.id).where(
                Group.telegram_id == chat.id
            )
        )

        group_id = result.scalar_one_or_none()

        if group_id is None:
            await message.reply_text(
                "📭 Для этой группы пока нет статистики."
            )
            return

        stats = await get_statistics(
            session,
            group_id,
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

        total_active_users = max(
            (
                item.active_users
                for item in stats
            ),
            default=0,
        )

    text = (
        "📊 Статистика группы\n\n"
        f"📨 Сообщений за 7 дней: "
        f"{total_messages}\n"
        f"👥 Активных участников: "
        f"{total_active_users}\n"
        f"⚠️ Нарушений: "
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

    if chat.type not in {
        "group",
        "supergroup",
    }:
        await message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                User.display_name,
                func.count(Message.id).label(
                    "count"
                ),
            )
            .join(
                Message,
                Message.user_id == User.id,
            )
            .join(
                Group,
                Message.group_id == Group.id,
            )
            .where(
                Group.telegram_id == chat.id,
                Message.is_deleted.is_(False),
            )
            .group_by(
                User.id,
                User.display_name,
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
        display_name = (
            user.display_name
            or "Без имени"
        )

        text += (
            f"{index}. "
            f"{display_name} — "
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

    if chat.type not in {
        "group",
        "supergroup",
    }:
        await message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                func.count(ModerationLog.id)
            )
            .join(
                Group,
                ModerationLog.group_id == Group.id,
            )
            .where(
                Group.telegram_id == chat.id
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

    if chat.type not in {
        "group",
        "supergroup",
    }:
        await message.reply_text(
            "Эта команда работает только в группе."
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Group.id).where(
                Group.telegram_id == chat.id
            )
        )

        group_id = result.scalar_one_or_none()

        if group_id is None:
            await message.reply_text(
                "📭 Пока нет статистики."
            )
            return

        stats = await get_statistics(
            session,
            group_id,
            days=7,
        )

    if not stats:
        await message.reply_text(
            "📭 Пока нет статистики."
        )
        return

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

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.ai.openai_compatible import create_ai_provider
from app.ai.prompts import build_summary_prompt
from app.config import get_settings
from app.db.models import Group, Message, Summary
from app.services.settings import get_or_create_settings

logger = logging.getLogger(__name__)


async def get_messages_for_period(
    session: AsyncSession,
    group_id: int,
    period_start: datetime,
    period_end: datetime,
) -> str:
    result = await session.execute(
        select(Message)
        .where(
            Message.group_id == group_id,
            Message.created_at >= period_start,
            Message.created_at < period_end,
            Message.is_deleted.is_(False),
        )
        .order_by(Message.created_at.asc())
    )

    messages = list(result.scalars().all())

    if not messages:
        return ""

    settings = get_settings()
    max_length = settings.max_message_length

    lines: list[str] = []

    for message in messages:
        text = message.text.strip()

        if not text:
            continue

        if len(text) > max_length:
            text = text[:max_length] + "..."

        timestamp = message.created_at.strftime(
            "%Y-%m-%d %H:%M"
        )

        lines.append(
            f"[{timestamp}] "
            f"user_id={message.user_id}: "
            f"{text}"
        )

    return "\n".join(lines)


async def generate_summary(
    session: AsyncSession,
    group_id: int,
    summary_type: str,
    period_start: datetime,
    period_end: datetime,
) -> str | None:
    context = await get_messages_for_period(
        session,
        group_id,
        period_start,
        period_end,
    )

    if not context:
        return None

    provider = create_ai_provider()

    prompts = build_summary_prompt(
        context=context,
    )

    try:
        result = await provider.generate(
            prompts,
            temperature=0.2,
            max_tokens=1500,
        )

    except Exception:
        logger.exception(
            "Failed to generate %s summary.",
            summary_type,
        )
        return None

    content = result.strip()

    if not content:
        return None

    summary = Summary(
        group_id=group_id,
        summary_type=summary_type,
        content=content,
        period_start=period_start,
        period_end=period_end,
    )

    session.add(summary)

    await session.flush()

    return content


async def send_summary_to_group(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    content: str,
    summary_type: str,
) -> bool:
    if summary_type == "daily":
        title = "📋 Ежедневная сводка"
    else:
        title = "📊 Еженедельная сводка"

    text = f"{title}\n\n{content}"

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
        )

        return True

    except TelegramError:
        logger.exception(
            "Failed to send summary to group %s.",
            chat_id,
        )
        return False


async def create_daily_summary_for_group(
    session: AsyncSession,
    context: ContextTypes.DEFAULT_TYPE,
    group: Group,
) -> bool:
    settings = await get_or_create_settings(
        session,
        group,
    )

    if not settings.daily_summary_enabled:
        return False

    now = datetime.utcnow()

    period_end = datetime(
        now.year,
        now.month,
        now.day,
    )

    period_start = period_end - timedelta(days=1)

    content = await generate_summary(
        session,
        group.id,
        "daily",
        period_start,
        period_end,
    )

    if not content:
        await session.commit()
        return False

    sent = await send_summary_to_group(
        context,
        group.telegram_id,
        content,
        "daily",
    )

    await session.commit()

    return sent


async def create_weekly_summary_for_group(
    session: AsyncSession,
    context: ContextTypes.DEFAULT_TYPE,
    group: Group,
) -> bool:
    settings = await get_or_create_settings(
        session,
        group,
    )

    if not settings.weekly_summary_enabled:
        return False

    now = datetime.utcnow()

    period_end = datetime(
        now.year,
        now.month,
        now.day,
    )

    period_start = period_end - timedelta(days=7)

    content = await generate_summary(
        session,
        group.id,
        "weekly",
        period_start,
        period_end,
    )

    if not content:
        await session.commit()
        return False

    sent = await send_summary_to_group(
        context,
        group.telegram_id,
        content,
        "weekly",
    )

    await session.commit()

    return sent


async def generate_daily_summaries(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        result = await session.execute(
            select(Group)
        )

        groups = list(result.scalars().all())

        for group in groups:
            try:
                await create_daily_summary_for_group(
                    session,
                    context,
                    group,
                )
            except Exception:
                logger.exception(
                    "Daily summary failed for group %s.",
                    group.telegram_id,
                )
                await session.rollback()


async def generate_weekly_summaries(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        result = await session.execute(
            select(Group)
        )

        groups = list(result.scalars().all())

        for group in groups:
            try:
                await create_weekly_summary_for_group(
                    session,
                    context,
                    group,
                )
            except Exception:
                logger.exception(
                    "Weekly summary failed for group %s.",
                    group.telegram_id,
                )
                await session.rollback()

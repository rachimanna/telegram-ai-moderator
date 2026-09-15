from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupStat, Message, ModerationLog


async def get_or_create_daily_stat(
    session: AsyncSession,
    group_id: int,
    day: date | None = None,
) -> GroupStat:
    target_day = day or datetime.utcnow().date()

    result = await session.execute(
        select(GroupStat).where(
            GroupStat.group_id == group_id,
            GroupStat.day == target_day,
        )
    )

    stat = result.scalar_one_or_none()

    if stat is None:
        stat = GroupStat(
            group_id=group_id,
            day=target_day,
            message_count=0,
            active_users=0,
            violations=0,
            deleted_messages=0,
            questions=0,
        )

        session.add(stat)
        await session.flush()

    return stat


async def increment_message_count(
    session: AsyncSession,
    group_id: int,
) -> None:
    stat = await get_or_create_daily_stat(
        session,
        group_id,
    )

    stat.message_count += 1


async def increment_violation_count(
    session: AsyncSession,
    group_id: int,
) -> None:
    stat = await get_or_create_daily_stat(
        session,
        group_id,
    )

    stat.violations += 1


async def increment_deleted_count(
    session: AsyncSession,
    group_id: int,
) -> None:
    stat = await get_or_create_daily_stat(
        session,
        group_id,
    )

    stat.deleted_messages += 1


async def increment_question_count(
    session: AsyncSession,
    group_id: int,
) -> None:
    stat = await get_or_create_daily_stat(
        session,
        group_id,
    )

    stat.questions += 1


async def get_statistics(
    session: AsyncSession,
    group_id: int,
    days: int = 7,
) -> list[GroupStat]:
    if days < 1:
        days = 1

    if days > 365:
        days = 365

    start_day = (
        datetime.utcnow().date()
        - timedelta(days=days - 1)
    )

    result = await session.execute(
        select(GroupStat)
        .where(
            GroupStat.group_id == group_id,
            GroupStat.day >= start_day,
        )
        .order_by(GroupStat.day.asc())
    )

    return list(result.scalars().all())


async def get_total_message_count(
    session: AsyncSession,
    group_id: int,
    days: int = 7,
) -> int:
    start_time = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        select(func.count(Message.id)).where(
            Message.group_id == group_id,
            Message.created_at >= start_time,
        )
    )

    return int(result.scalar_one() or 0)


async def get_total_moderation_actions(
    session: AsyncSession,
    group_id: int,
    days: int = 7,
) -> int:
    start_time = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        select(func.count(ModerationLog.id)).where(
            ModerationLog.group_id == group_id,
            ModerationLog.created_at >= start_time,
        )
    )

    return int(result.scalar_one() or 0)

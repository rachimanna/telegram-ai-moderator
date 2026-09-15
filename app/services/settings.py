from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Group, GroupSettings


async def get_or_create_group(
    session: AsyncSession,
    telegram_group_id: int,
    title: str,
) -> Group:
    result = await session.execute(
        select(Group).where(
            Group.telegram_id == telegram_group_id
        )
    )

    group = result.scalar_one_or_none()

    if group is None:
        group = Group(
            telegram_id=telegram_group_id,
            title=title,
        )

        session.add(group)
        await session.flush()

    return group


async def get_or_create_settings(
    session: AsyncSession,
    group: Group,
) -> GroupSettings:
    if group.settings is not None:
        return group.settings

    result = await session.execute(
        select(GroupSettings).where(
            GroupSettings.group_id == group.id
        )
    )

    settings = result.scalar_one_or_none()

    if settings is None:
        app_settings = get_settings()

        settings = GroupSettings(
            group_id=group.id,
            moderation_enabled=(
                app_settings.default_moderation_enabled
            ),
            ai_answers_enabled=(
                app_settings.default_ai_answers_enabled
            ),
            strictness=app_settings.default_strictness,
            moderation_action=(
                app_settings.default_moderation_action
            ),
            warning_threshold=(
                app_settings.default_warning_threshold
            ),
            daily_summary_enabled=(
                app_settings.daily_summary_enabled
            ),
            weekly_summary_enabled=(
                app_settings.weekly_summary_enabled
            ),
            excluded_user_ids=[],
            excluded_words=[],
        )

        session.add(settings)
        await session.flush()

    return settings


async def update_settings(
    session: AsyncSession,
    group: Group,
    **changes,
) -> GroupSettings:
    settings = await get_or_create_settings(
        session,
        group,
    )

    allowed_fields = {
        "moderation_enabled",
        "ai_answers_enabled",
        "strictness",
        "moderation_action",
        "warning_threshold",
        "daily_summary_enabled",
        "weekly_summary_enabled",
        "excluded_user_ids",
        "excluded_words",
    }

    for field, value in changes.items():
        if field in allowed_fields:
            setattr(settings, field, value)

    await session.flush()

    return settings

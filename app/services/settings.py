from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Group, GroupSettings


ALLOWED_STRICTNESS = {
    "low",
    "medium",
    "high",
}

ALLOWED_ACTIONS = {
    "warn",
    "delete",
    "restrict",
    "notify",
}


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

    elif group.title != title:
        group.title = title

        await session.flush()

    return group


async def get_or_create_settings(
    session: AsyncSession,
    group: Group,
) -> GroupSettings:
    result = await session.execute(
        select(GroupSettings).where(
            GroupSettings.group_id == group.id
        )
    )

    settings = result.scalar_one_or_none()

    if settings is not None:
        return settings

    app_settings = get_settings()

    settings = GroupSettings(
        group_id=group.id,
        moderation_enabled=(
            app_settings.default_moderation_enabled
        ),
        ai_answers_enabled=(
            app_settings.default_ai_answers_enabled
        ),
        strictness=(
            app_settings.default_strictness
        ),
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
        if field not in allowed_fields:
            continue

        if field == "strictness":
            if value not in ALLOWED_STRICTNESS:
                raise ValueError(
                    "Недопустимый уровень строгости."
                )

        if field == "moderation_action":
            if value not in ALLOWED_ACTIONS:
                raise ValueError(
                    "Недопустимое действие модерации."
                )

        if field == "warning_threshold":
            try:
                value = int(value)
            except (
                TypeError,
                ValueError,
            ):
                raise ValueError(
                    "Порог предупреждений должен быть числом."
                )

            if not 1 <= value <= 20:
                raise ValueError(
                    "Порог предупреждений должен быть "
                    "от 1 до 20."
                )

        if field in {
            "moderation_enabled",
            "ai_answers_enabled",
            "daily_summary_enabled",
            "weekly_summary_enabled",
        }:
            if not isinstance(value, bool):
                raise ValueError(
                    f"{field} должен быть True или False."
                )

        if field in {
            "excluded_user_ids",
            "excluded_words",
        }:
            if not isinstance(value, list):
                raise ValueError(
                    f"{field} должен быть списком."
                )

        setattr(
            settings,
            field,
            value,
        )

    await session.flush()

    return settings

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import ChatPermissions
from telegram.error import TelegramError

from app.ai.openai_compatible import create_ai_provider
from app.ai.prompts import build_moderation_prompt
from app.db.models import (
    Group,
    Message,
    ModerationLog,
    Warning,
)
from app.moderation.classifier import (
    ModerationResult,
    parse_moderation_result,
)
from app.moderation.policy import decide_action
from app.services.analytics import (
    increment_active_user,
    increment_deleted_count,
    increment_message_count,
    increment_violation_count,
)
from app.services.settings import get_or_create_settings
from app.services.users import get_or_create_user


logger = logging.getLogger(__name__)


MESSAGE_WINDOW = timedelta(seconds=60)

FLOOD_WARNING_LIMIT = 10
FLOOD_RESTRICT_LIMIT = 20

REPEAT_WINDOW = timedelta(minutes=10)

REPEAT_WARNING_LIMIT = 3
REPEAT_RESTRICT_LIMIT = 5


_recent_messages: dict[
    tuple[int, int],
    deque[tuple[datetime, str]],
] = defaultdict(deque)


def normalize_text(
    text: str,
) -> str:
    return " ".join(
        text.lower().split()
    ).strip()


def register_local_message(
    chat_id: int,
    user_id: int,
    text: str,
) -> tuple[int, int]:
    now = datetime.utcnow()

    key = (
        chat_id,
        user_id,
    )

    history = _recent_messages[key]

    while history:
        timestamp, _ = history[0]

        if (
            now - timestamp
            <= REPEAT_WINDOW
        ):
            break

        history.popleft()

    normalized = normalize_text(
        text
    )

    history.append(
        (
            now,
            normalized,
        )
    )

    flood_count = sum(
        1
        for timestamp, _ in history
        if (
            now - timestamp
            <= MESSAGE_WINDOW
        )
    )

    repeat_count = sum(
        1
        for _, previous_text in history
        if (
            previous_text == normalized
            and normalized
        )
    )

    return (
        flood_count,
        repeat_count,
    )


def cleanup_local_state() -> None:
    now = datetime.utcnow()

    empty_keys = []

    for key, history in (
        _recent_messages.items()
    ):
        while history:
            timestamp, _ = history[0]

            if (
                now - timestamp
                <= REPEAT_WINDOW
            ):
                break

            history.popleft()

        if not history:
            empty_keys.append(key)

    for key in empty_keys:
        _recent_messages.pop(
            key,
            None,
        )


async def get_group(
    session: AsyncSession,
    chat_id: int,
    chat_title: str,
) -> Group:
    result = await session.execute(
        select(Group).where(
            Group.telegram_id == chat_id
        )
    )

    group = (
        result.scalar_one_or_none()
    )

    if group is None:
        group = Group(
            telegram_id=chat_id,
            title=chat_title,
        )

        session.add(group)

        await session.flush()

    elif group.title != chat_title:
        group.title = chat_title

        await session.flush()

    return group


async def is_telegram_admin(
    context,
    chat_id: int,
    user_id: int,
) -> bool:
    try:
        member = (
            await context.bot.get_chat_member(
                chat_id,
                user_id,
            )
        )

        return member.status in {
            "administrator",
            "creator",
        }

    except TelegramError:
        logger.warning(
            "Could not check admin status: "
            "chat=%s user=%s",
            chat_id,
            user_id,
        )

        return False


async def create_warning(
    session: AsyncSession,
    group_id: int,
    user_id: int,
    reason: str,
) -> int:
    warning = Warning(
        group_id=group_id,
        user_id=user_id,
        reason=reason,
    )

    session.add(warning)

    await session.flush()

    result = await session.execute(
        select(Warning).where(
            Warning.group_id == group_id,
            Warning.user_id == user_id,
        )
    )

    warnings = list(
        result.scalars().all()
    )

    return len(warnings)


async def log_moderation(
    session: AsyncSession,
    group_id: int,
    user_id: int | None,
    message_id: int | None,
    action: str,
    category: str | None,
    reason: str | None,
) -> None:
    log = ModerationLog(
        group_id=group_id,
        user_id=user_id,
        message_id=message_id,
        action=action,
        category=category,
        reason=reason,
    )

    session.add(log)

    await session.flush()


async def delete_message(
    context,
    chat_id: int,
    telegram_message_id: int,
) -> bool:
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=telegram_message_id,
        )

        return True

    except TelegramError:
        logger.warning(
            "Failed to delete message: "
            "chat=%s message=%s",
            chat_id,
            telegram_message_id,
        )

        return False


async def restrict_user(
    context,
    chat_id: int,
    user_id: int,
    minutes: int,
) -> bool:
    until_date = (
        datetime.utcnow()
        + timedelta(minutes=minutes)
    )

    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date,
        )

        return True

    except TelegramError:
        logger.warning(
            "Failed to restrict user: "
            "chat=%s user=%s",
            chat_id,
            user_id,
        )

        return False


async def analyze_with_ai(
    text: str,
    username: str,
) -> ModerationResult:
    provider = create_ai_provider()

    messages = build_moderation_prompt(
        username=username,
        message_text=text,
    )

    raw_response = await provider.generate(
        messages,
        temperature=0.0,
        max_tokens=500,
    )

    return parse_moderation_result(
        raw_response
    )


async def moderate_message(
    session: AsyncSession,
    context,
    chat_id: int,
    chat_title: str,
    user_id: int,
    username: str,
    display_name: str,
    telegram_message_id: int,
    text: str,
) -> str:
    group = await get_group(
        session,
        chat_id,
        chat_title,
    )

    settings = await get_or_create_settings(
        session,
        group,
    )

    telegram_user = await get_or_create_user(
        session,
        telegram_id=user_id,
        username=username.lstrip("@")
        if username.startswith("@")
        else None,
        display_name=display_name,
    )

    message = Message(
        group_id=group.id,
        user_id=telegram_user.id,
        telegram_message_id=(
            telegram_message_id
        ),
        text=text,
    )

    session.add(message)

    await session.flush()

    await increment_message_count(
        session,
        group.id,
    )

    await increment_active_user(
        session,
        group.id,
        telegram_user.id,
    )

    # Administrators are not moderated.
    if await is_telegram_admin(
        context,
        chat_id,
        user_id,
    ):
        await session.commit()

        cleanup_local_state()

        return "ignored_admin"

    # Local anti-flood protection.
    flood_count, repeat_count = (
        register_local_message(
            chat_id,
            user_id,
            text,
        )
    )

    if (
        flood_count
        >= FLOOD_RESTRICT_LIMIT
    ):
        deleted = await delete_message(
            context,
            chat_id,
            telegram_message_id,
        )

        restricted = await restrict_user(
            context,
            chat_id,
            user_id,
            minutes=10,
        )

        reason = (
            "Обнаружен сильный флуд."
        )

        await increment_violation_count(
            session,
            group.id,
        )

        if deleted:
            message.is_deleted = True

            await increment_deleted_count(
                session,
                group.id,
            )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "restrict",
            "flooding",
            reason,
        )

        await session.commit()

        cleanup_local_state()

        return (
            "restrict"
            if restricted
            else "delete"
        )

    if (
        flood_count
        >= FLOOD_WARNING_LIMIT
    ):
        warning_count = await create_warning(
            session,
            group.id,
            telegram_user.id,
            "Обнаружен повышенный уровень флуда.",
        )

        await increment_violation_count(
            session,
            group.id,
        )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "warn",
            "flooding",
            "Обнаружен повышенный уровень флуда.",
        )

        await session.commit()

        cleanup_local_state()

        return "warn"

    if (
        repeat_count
        >= REPEAT_RESTRICT_LIMIT
    ):
        deleted = await delete_message(
            context,
            chat_id,
            telegram_message_id,
        )

        restricted = await restrict_user(
            context,
            chat_id,
            user_id,
            minutes=10,
        )

        reason = (
            "Обнаружено многократное "
            "повторение одинаковых сообщений."
        )

        await increment_violation_count(
            session,
            group.id,
        )

        if deleted:
            message.is_deleted = True

            await increment_deleted_count(
                session,
                group.id,
            )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "restrict",
            "repetition",
            reason,
        )

        await session.commit()

        cleanup_local_state()

        return (
            "restrict"
            if restricted
            else "delete"
        )

    if (
        repeat_count
        >= REPEAT_WARNING_LIMIT
    ):
        await create_warning(
            session,
            group.id,
            telegram_user.id,
            "Обнаружено повторение одинаковых сообщений.",
        )

        await increment_violation_count(
            session,
            group.id,
        )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "warn",
            "repetition",
            "Обнаружено повторение одинаковых сообщений.",
        )

        await session.commit()

        cleanup_local_state()

        return "warn"

    # AI moderation can be disabled independently.
    if not settings.moderation_enabled:
        await session.commit()

        cleanup_local_state()

        return "allowed"

    try:
        result = await analyze_with_ai(
            text=text,
            username=username,
        )

    except Exception:
        logger.exception(
            "AI moderation failed."
        )

        await session.commit()

        cleanup_local_state()

        return "allowed"

    if not result.violation:
        await session.commit()

        cleanup_local_state()

        return "allowed"

    await increment_violation_count(
        session,
        group.id,
    )

    decision = decide_action(
        violation=result.violation,
        category=result.category,
        severity=result.severity,
        confidence=result.confidence,
        strictness=settings.strictness,
        configured_action=settings.moderation_action,
    )

    action = decision.action

    if action == "warn":
        warning_count = await create_warning(
            session,
            group.id,
            telegram_user.id,
            result.reason,
        )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "warn",
            result.category,
            result.reason,
        )

        if (
            warning_count
            >= settings.warning_threshold
        ):
            restricted = await restrict_user(
                context,
                chat_id,
                user_id,
                minutes=10,
            )

            if restricted:
                await log_moderation(
                    session,
                    group.id,
                    telegram_user.id,
                    message.id,
                    "restrict",
                    result.category,
                    "Достигнут лимит предупреждений.",
                )

                await session.commit()

                cleanup_local_state()

                return "restrict"

    elif action == "delete":
        deleted = await delete_message(
            context,
            chat_id,
            telegram_message_id,
        )

        if deleted:
            message.is_deleted = True

            await increment_deleted_count(
                session,
                group.id,
            )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "delete",
            result.category,
            result.reason,
        )

    elif action == "restrict":
        deleted = await delete_message(
            context,
            chat_id,
            telegram_message_id,
        )

        restricted = await restrict_user(
            context,
            chat_id,
            user_id,
            minutes=10,
        )

        if deleted:
            message.is_deleted = True

            await increment_deleted_count(
                session,
                group.id,
            )

        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "restrict",
            result.category,
            result.reason,
        )

        await session.commit()

        cleanup_local_state()

        return (
            "restrict"
            if restricted
            else "delete"
        )

    elif action == "notify":
        await log_moderation(
            session,
            group.id,
            telegram_user.id,
            message.id,
            "notify",
            result.category,
            result.reason,
        )

    await session.commit()

    cleanup_local_state()

    return action

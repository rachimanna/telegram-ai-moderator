import logging
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import ChatPermissions
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.ai.openai_compatible import create_ai_provider
from app.ai.prompts import build_moderation_prompt
from app.db.models import Message, ModerationLog, Warning
from app.moderation.classifier import parse_moderation_result
from app.moderation.policy import decide_action
from app.services.analytics import (
    increment_deleted_count,
    increment_violation_count,
)
from app.services.settings import (
    get_or_create_group,
    get_or_create_settings,
)
from app.services.users import get_or_create_user

logger = logging.getLogger(__name__)


_message_times: dict[
    tuple[int, int],
    deque[datetime],
] = defaultdict(deque)

_recent_texts: dict[
    tuple[int, int],
    deque[str],
] = defaultdict(deque)


FLOOD_WINDOW_SECONDS = 60
FLOOD_WARNING_LIMIT = 10
FLOOD_RESTRICT_LIMIT = 20

REPEAT_WINDOW = 10
REPEAT_WARNING_LIMIT = 3
REPEAT_RESTRICT_LIMIT = 5


def normalize_text(text: str) -> str:
    text = text.lower().strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def remember_message(
    chat_id: int,
    user_id: int,
    text: str,
    now: datetime,
) -> tuple[int, int]:
    key = (chat_id, user_id)

    times = _message_times[key]

    times.append(now)

    cutoff = now - timedelta(
        seconds=FLOOD_WINDOW_SECONDS
    )

    while times and times[0] < cutoff:
        times.popleft()

    normalized = normalize_text(text)

    recent = _recent_texts[key]

    if normalized:
        recent.append(normalized)

    while len(recent) > REPEAT_WINDOW:
        recent.popleft()

    return key


def detect_local_flood(
    chat_id: int,
    user_id: int,
    text: str,
    now: datetime,
) -> tuple[str | None, str]:
    key = remember_message(
        chat_id,
        user_id,
        text,
        now,
    )

    times = _message_times[key]
    recent = _recent_texts[key]

    message_count = len(times)

    if message_count >= FLOOD_RESTRICT_LIMIT:
        return (
            "flooding",
            (
                f"User sent {message_count} messages "
                f"in {FLOOD_WINDOW_SECONDS} seconds."
            ),
        )

    if message_count >= FLOOD_WARNING_LIMIT:
        return (
            "flooding",
            (
                f"User sent {message_count} messages "
                f"in {FLOOD_WINDOW_SECONDS} seconds."
            ),
        )

    normalized = normalize_text(text)

    if normalized:
        repetitions = sum(
            1
            for item in recent
            if item == normalized
        )

        if repetitions >= REPEAT_RESTRICT_LIMIT:
            return (
                "repetition",
                (
                    f"Same message repeated "
                    f"{repetitions} times."
                ),
            )

        if repetitions >= REPEAT_WARNING_LIMIT:
            return (
                "repetition",
                (
                    f"Same message repeated "
                    f"{repetitions} times."
                ),
            )

    return None, ""


async def is_telegram_admin(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> bool:
    try:
        member = await context.bot.get_chat_member(
            chat_id=chat_id,
            user_id=user_id,
        )

    except TelegramError:
        logger.exception(
            "Failed to check Telegram admin status."
        )
        return False

    return member.status in {
        "administrator",
        "creator",
    }


async def get_warning_count(
    session: AsyncSession,
    group_id: int,
    user_id: int,
) -> int:
    result = await session.execute(
        select(func.count(Warning.id)).where(
            Warning.group_id == group_id,
            Warning.user_id == user_id,
        )
    )

    return int(result.scalar_one() or 0)


async def add_warning(
    session: AsyncSession,
    group_id: int,
    user_id: int,
    reason: str,
    severity: int,
) -> int:
    warning = Warning(
        group_id=group_id,
        user_id=user_id,
        reason=reason,
        severity=severity,
    )

    session.add(warning)

    await session.flush()

    return await get_warning_count(
        session,
        group_id,
        user_id,
    )


async def log_moderation(
    session: AsyncSession,
    *,
    group_id: int,
    user_id: int | None,
    message_id: int | None,
    action: str,
    reason: str,
    category: str,
    metadata: dict | None = None,
) -> None:
    log = ModerationLog(
        group_id=group_id,
        user_id=user_id,
        message_id=message_id,
        action=action,
        reason=reason,
        category=category,
        metadata_json=metadata or {},
    )

    session.add(log)


async def delete_message(
    context: ContextTypes.DEFAULT_TYPE,
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
        logger.exception(
            "Failed to delete Telegram message."
        )
        return False


async def restrict_user(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    minutes: int = 10,
) -> bool:
    until_date = datetime.utcnow() + timedelta(
        minutes=minutes
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
        logger.exception(
            "Failed to restrict Telegram user."
        )
        return False


async def send_warning(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    warning_count: int,
    reason: str,
) -> None:
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ Предупреждение пользователю.\n\n"
                f"Причина: {reason}\n"
                f"Предупреждений: {warning_count}"
            ),
        )

    except TelegramError:
        logger.exception(
            "Failed to send moderation warning."
        )


async def analyze_with_ai(
    username: str,
    text: str,
):
    provider = create_ai_provider()

    prompts = build_moderation_prompt(
        username=username,
        message_text=text,
    )

    raw_response = await provider.generate(
        prompts,
        temperature=0.0,
        max_tokens=400,
        response_format={
            "type": "json_object"
        },
    )

    return parse_moderation_result(
        raw_response
    )


async def moderate_message(
    session: AsyncSession,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    chat_title: str,
    user_id: int,
    username: str,
    telegram_message_id: int,
    text: str,
) -> str:
    """
    Moderate one Telegram message.

    Returns the action that was performed:
    ignore, warn, delete, restrict.
    """

    group = await get_or_create_group(
        session,
        telegram_group_id=chat_id,
        title=chat_title,
    )

    settings = await get_or_create_settings(
        session,
        group,
    )

    telegram_user = await get_or_create_user(
        session,
        telegram_id=user_id,
        username=(
            username.lstrip("@")
            if username.startswith("@")
            else None
        ),
        display_name=username,
    )

    message = Message(
        group_id=group.id,
        user_id=telegram_user.id,
        telegram_message_id=telegram_message_id,
        text=text,
    )

    session.add(message)

    await session.flush()

    if user_id in settings.excluded_user_ids:
        await session.commit()

        return "ignore"

    if await is_telegram_admin(
        context,
        chat_id,
        user_id,
    ):
        await session.commit()

        return "ignore"

    now = datetime.utcnow()

    local_category, local_reason = detect_local_flood(
        chat_id,
        user_id,
        text,
        now,
    )

    if local_category is not None:
        if local_category == "flooding":
            action = (
                "restrict"
                if len(
                    _message_times[
                        (chat_id, user_id)
                    ]
                ) >= FLOOD_RESTRICT_LIMIT
                else "warn"
            )
        else:
            action = (
                "restrict"
                if len(
                    _recent_texts[
                        (chat_id, user_id)
                    ]
                ) >= REPEAT_RESTRICT_LIMIT
                else "warn"
            )

        if action == "warn":
            warning_count = await add_warning(
                session,
                group.id,
                telegram_user.id,
                local_reason,
                1,
            )

            await send_warning(
                context,
                chat_id,
                user_id,
                warning_count,
                local_reason,
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

            if not restricted:
                action = (
                    "delete"
                    if deleted
                    else "warn"
                )

        await increment_violation_count(
            session,
            group.id,
        )

        await log_moderation(
            session,
            group_id=group.id,
            user_id=telegram_user.id,
            message_id=message.id,
            action=action,
            reason=local_reason,
            category=local_category,
            metadata={
                "source": "local_antiflood",
            },
        )

        await session.commit()

        return action

    if not settings.moderation_enabled:
        await session.commit()

        return "ignore"

    try:
        result = await analyze_with_ai(
            username=username,
            text=text,
        )

    except Exception:
        logger.exception(
            "AI moderation failed."
        )

        await session.commit()

        return "ignore"

    if not result.violation:
        await session.commit()

        return "ignore"

    decision = decide_action(
        violation=result.violation,
        category=result.category,
        severity=result.severity,
        confidence=result.confidence,
        strictness=settings.strictness,
        configured_action=settings.moderation_action,
    )

    action = decision.action

    warning_count = 0

    if action == "warn":
        warning_count = await add_warning(
            session,
            group.id,
            telegram_user.id,
            result.reason,
            result.severity,
        )

        await send_warning(
            context,
            chat_id,
            user_id,
            warning_count,
            result.reason,
        )

        if warning_count >= settings.warning_threshold:
            action = "restrict"

    if action == "delete":
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
        else:
            action = "warn"

    if action == "restrict":
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

        if not restricted:
            action = (
                "delete"
                if deleted
                else "warn"
            )

    if action == "warn" and warning_count == 0:
        warning_count = await add_warning(
            session,
            group.id,
            telegram_user.id,
            result.reason,
            result.severity,
        )

        await send_warning(
            context,
            chat_id,
            user_id,
            warning_count,
            result.reason,
        )

    await increment_violation_count(
        session,
        group.id,
    )

    await log_moderation(
        session,
        group_id=group.id,
        user_id=telegram_user.id,
        message_id=message.id,
        action=action,
        reason=result.reason,
        category=result.category,
        metadata={
            "confidence": result.confidence,
            "severity": result.severity,
            "warning_count": warning_count,
            "policy_reason": decision.reason,
            "source": "ai",
        },
    )

    await session.commit()

    return action

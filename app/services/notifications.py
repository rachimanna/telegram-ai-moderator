import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModerationLog

logger = logging.getLogger(__name__)


async def check_critical_issues(
    session: AsyncSession,
    group_id: int,
) -> None:
    """
    Check for critical issues in the group and send notifications if needed.

    This function is called after moderation actions to check if there are
    critical patterns that need admin attention.

    Args:
        session: Database session
        group_id: ID of the group to check
    """
    # Placeholder implementation
    # Can be extended to:
    # - Count recent violations
    # - Detect spam patterns
    # - Send admin notifications
    # - Trigger escalation actions
    pass


DEFAULT_NOTIFICATIONS_WINDOW_HOURS = 24
DEFAULT_NOTIFICATIONS_LIMIT = 10


async def get_recent_notifications(
    session: AsyncSession,
    group_id: int,
    hours: int = DEFAULT_NOTIFICATIONS_WINDOW_HOURS,
    limit: int = DEFAULT_NOTIFICATIONS_LIMIT,
) -> list[ModerationLog]:
    """
    Возвращает последние записи журнала модерации (`ModerationLog`) для
    группы за последние `hours` часов, отсортированные от новых к старым.

    Используется командой `/notifications` (`app.handlers.commands`) как
    источник "непрочитанных уведомлений": в проекте пока нет отдельной
    таблицы уведомлений с флагом "прочитано/не прочитано", поэтому единственный
    практичный источник событий, которые могут заинтересовать администратора —
    это журнал действий модерации.

    Если в будущем `check_critical_issues` перестанет быть заглушкой и начнёт
    реально формировать отдельные уведомления (например, в новую таблицу),
    эту функцию нужно будет переключить на новый источник данных, не меняя
    сигнатуру — вызывающий код (`/notifications`) менять не придётся.

    Args:
        session: Асинхронная сессия БД.
        group_id: Внутренний (не telegram) ID группы.
        hours: Ширина окна выборки в часах.
        limit: Максимальное количество возвращаемых записей.

    Returns:
        Список `ModerationLog`, максимум `limit` штук, новые сначала.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    result = await session.execute(
        select(ModerationLog)
        .where(
            ModerationLog.group_id == group_id,
            ModerationLog.created_at >= cutoff,
        )
        .order_by(ModerationLog.created_at.desc())
        .limit(limit)
    )

    return list(result.scalars().all())

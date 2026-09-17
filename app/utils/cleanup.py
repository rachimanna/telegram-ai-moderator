import logging
from datetime import datetime, timedelta

from telegram.ext import ContextTypes

from app.services.moderation import _recent_messages

logger = logging.getLogger(__name__)

DEFAULT_MESSAGE_AGE_HOURS = 24


def purge_stale_entries(
    recent_messages_dict: dict,
    message_age_hours: int = DEFAULT_MESSAGE_AGE_HOURS,
) -> tuple[int, int]:
    """
    Выполняет ОДИН проход очистки словаря `_recent_messages`
    (in-memory состояние антифлуд/антиповтор-детектора из
    `app.services.moderation`) от записей старше `message_age_hours`.

    Это чистая синхронная функция без циклов и без `asyncio.sleep` —
    единственный побочный эффект — мутация переданного словаря. Вынесена
    отдельно от `cleanup_job`, чтобы её было легко покрыть модульным тестом
    без необходимости иметь дело с `telegram.ext.ContextTypes`.

    Args:
        recent_messages_dict: Глобальный словарь `_recent_messages` из
            `app.services.moderation` (или совместимый по интерфейсу).
        message_age_hours: Возраст записей для удаления, в часах.

    Returns:
        Кортеж `(deleted_count, remaining_keys)`:
        сколько отдельных сообщений было удалено и сколько пар
        (chat_id, user_id) осталось в словаре после очистки.
    """
    now = datetime.utcnow()
    cutoff_time = now - timedelta(hours=message_age_hours)

    keys_to_delete = []
    deleted_count = 0

    for key, history in recent_messages_dict.items():
        while history:
            timestamp, _ = history[0]

            if timestamp > cutoff_time:
                break

            history.popleft()
            deleted_count += 1

        if not history:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        del recent_messages_dict[key]

    return deleted_count, len(recent_messages_dict)


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Колбэк JobQueue: выполняет ОДНУ итерацию очистки in-memory состояния
    антифлуд/антиповтор-детектора и сразу завершается — без бесконечного
    цикла `while True` внутри.

    Регистрируется через `job_queue.run_repeating(cleanup_job, interval=...)`
    — планировщик сам будет вызывать эту функцию периодически. Раньше сюда
    передавалась `lambda`, оборачивающая корутину с бесконечным циклом:
    `run_repeating` требует именно async-функцию-колбэк (проверяется через
    `inspect.iscoroutinefunction`), поэтому лямбда никогда не запускала
    исходную корутину — а если бы запустила, бесконечный `while True`
    навсегда заблокировал бы обработку остальных задач `JobQueue`.

    Любые исключения ловятся и логируются, но не пробрасываются наружу,
    чтобы один неудачный проход очистки не "уронил" планировщик задач.
    """
    try:
        deleted_count, remaining_keys = purge_stale_entries(_recent_messages)

        logger.info(
            "Memory cleanup: deleted %s old messages, "
            "%s active user/chat pairs remaining",
            deleted_count,
            remaining_keys,
        )

    except Exception:
        logger.exception("Error during scheduled memory cleanup job.")


async def cleanup_old_messages(
    recent_messages_dict: dict,
    message_age_hours: int = DEFAULT_MESSAGE_AGE_HOURS,
) -> tuple[int, int]:
    """
    Совместимость со старым именем/сигнатурой (без параметра
    `interval_seconds`, который раньше означал `asyncio.sleep` внутри
    бесконечного цикла и здесь не нужен). Выполняет один проход очистки
    через `purge_stale_entries` и возвращает `(deleted_count, remaining_keys)`.

    Оставлена на случай, если что-то ещё импортирует эту функцию напрямую
    (например, тесты). Для регистрации в `JobQueue` используйте `cleanup_job`.
    """
    return purge_stale_entries(recent_messages_dict, message_age_hours)

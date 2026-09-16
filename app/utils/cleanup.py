import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def cleanup_old_messages(
    recent_messages_dict: dict,
    interval_seconds: int = 3600,
    message_age_hours: int = 24,
) -> None:
    """
    Периодически очищает старые сообщения из памяти.
    
    Запускается каждый `interval_seconds` (по умолчанию 1 час).
    Удаляет сообщения старше `message_age_hours` (по умолчанию 24 часа).
    
    Args:
        recent_messages_dict: Глобальный словарь _recent_messages из moderation.py
        interval_seconds: Интервал очистки в секундах
        message_age_hours: Возраст сообщений для удаления в часах
    """
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            
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
            
            remaining_keys = len(recent_messages_dict)
            
            logger.info(
                f"Memory cleanup: deleted {deleted_count} old messages, "
                f"{remaining_keys} active user/chat pairs remaining"
            )
            
        except Exception as e:
            logger.error(
                f"Error in cleanup_old_messages: {e}",
                exc_info=True,
            )
            await asyncio.sleep(interval_seconds)

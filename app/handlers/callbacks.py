import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query

    if query is None:
        return

    try:
        await query.answer()

    except Exception:
        logger.exception(
            "Failed to answer callback query."
        )

    data = query.data or ""

    if data == "settings":
        await show_settings(
            update,
            context,
        )
        return

    if data == "moderation_toggle":
        await query.answer(
            "Настройки модерации подключим следующим шагом."
        )
        return

    if data == "ai_toggle":
        await query.answer(
            "Настройки AI подключим следующим шагом."
        )
        return

    if data == "strictness":
        await query.answer(
            "Настройка строгости подключим следующим шагом."
        )
        return

    if data == "summary":
        await query.answer(
            "Настройка сводок подключим следующим шагом."
        )
        return

    if data == "back":
        await query.answer(
            "Назад"
        )
        return

    logger.warning(
        "Unknown callback data: %s",
        data,
    )


async def show_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query

    if query is None:
        return

    try:
        await query.edit_message_text(
            "⚙️ Настройки бота\n\n"
            "Выберите нужный раздел.\n\n"
            "Полное управление настройками "
            "подключим следующим шагом."
        )

    except Exception:
        logger.exception(
            "Failed to display settings."
        )


def register_callback_handlers(
    application,
) -> None:
    application.add_handler(
        CallbackQueryHandler(
            handle_callback
        )
    )

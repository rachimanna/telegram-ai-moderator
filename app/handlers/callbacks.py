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


def register_callback_handlers(
    application,
) -> None:
    application.add_handler(
        CallbackQueryHandler(
            handle_callback
        )
    )

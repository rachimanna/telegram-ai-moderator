import logging

from telegram.ext import (
    Application,
    ApplicationBuilder,
)

from app.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.handlers.callbacks import register_callback_handlers
from app.handlers.commands import register_command_handlers
from app.handlers.messages import register_message_handlers
from app.logging_setup import setup_logging
from app.services.summaries import (
    generate_daily_summaries,
    generate_weekly_summaries,
)


logger = logging.getLogger(__name__)


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all
        )


async def post_init(
    application: Application,
) -> None:
    logger.info(
        "Initializing database..."
    )

    await initialize_database()

    logger.info(
        "Database initialized."
    )

    job_queue = application.job_queue

    if job_queue is None:
        logger.warning(
            "Job queue is unavailable."
        )
        return

    settings = get_settings()

    # Daily summaries.
    if settings.daily_summary_enabled:
        job_queue.run_daily(
            generate_daily_summaries,
            time=__import__(
                "datetime"
            ).time(
                hour=settings.daily_summary_hour,
                minute=0,
            ),
            name="daily_summaries",
        )

    # Weekly summaries.
    if settings.weekly_summary_enabled:
        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        weekday = weekday_map.get(
            settings.weekly_summary_day.lower(),
            6,
        )

        job_queue.run_daily(
            generate_weekly_summaries,
            time=__import__(
                "datetime"
            ).time(
                hour=settings.weekly_summary_hour,
                minute=0,
            ),
            days=(
                weekday,
            ),
            name="weekly_summaries",
        )

    logger.info(
        "Scheduled jobs configured."
    )


async def post_shutdown(
    application: Application,
) -> None:
    from app.db.session import close_database

    logger.info(
        "Closing database connection..."
    )

    await close_database()

    logger.info(
        "Database connection closed."
    )


def build_application() -> Application:
    settings = get_settings()

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_command_handlers(
        application
    )

    register_callback_handlers(
        application
    )

    register_message_handlers(
        application
    )

    return application


def run() -> None:
    settings = get_settings()

    setup_logging(
        settings.log_level
    )

    logger.info(
        "Starting Telegram AI Moderator..."
    )

    application = build_application()

    application.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
        ],
        drop_pending_updates=True,
    )

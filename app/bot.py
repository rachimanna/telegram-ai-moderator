import logging
import os
from datetime import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    MenuButtonCommands,
    Update,
)
from telegram.ext import Application, ApplicationBuilder

from app.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.handlers.admin import register_admin_handlers
from app.handlers.callbacks import register_callback_handlers
from app.handlers.commands import register_command_handlers
from app.handlers.messages import register_message_handlers
from app.handlers.stats import register_stats_handlers
from app.logging_setup import setup_logging
from app.services.summaries import (
    generate_daily_summaries,
    generate_weekly_summaries,
)

logger = logging.getLogger(__name__)

telegram_application: Application | None = None


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def setup_bot_commands(application: Application) -> None:
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Помощь и список команд"),
        BotCommand("today", "Что обсуждали сегодня"),
        BotCommand("stats", "Общая статистика"),
        BotCommand("top", "Самые активные участники"),
        BotCommand("activity", "Активность за неделю"),
        BotCommand("moderation", "Журнал модерации"),
        BotCommand("settings", "Настройки AI-модерации"),
    ]

    await application.bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeAllPrivateChats(),
    )

    await application.bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeAllGroupChats(),
    )

    await application.bot.set_my_commands(
        commands=commands,
    )

    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonCommands(),
    )

    logger.info("Telegram bot commands configured.")


async def post_init(application: Application) -> None:
    logger.info("Initializing database...")

    await initialize_database()

    logger.info("Database initialized.")

    await setup_bot_commands(application)

    job_queue = application.job_queue

    if job_queue is None:
        logger.warning("Job queue is unavailable.")
        return

    settings = get_settings()

    if settings.daily_summary_enabled:
        job_queue.run_daily(
            generate_daily_summaries,
            time=time(
                hour=settings.daily_summary_hour,
                minute=0,
            ),
            name="daily_summaries",
        )

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
            time=time(
                hour=settings.weekly_summary_hour,
                minute=0,
            ),
            days=(weekday,),
            name="weekly_summaries",
        )

    logger.info("Scheduled jobs configured.")


async def post_shutdown(application: Application) -> None:
    from app.db.session import close_database

    logger.info("Closing database connection...")

    await close_database()

    logger.info("Database connection closed.")


def build_application() -> Application:
    settings = get_settings()

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_command_handlers(application)
    register_admin_handlers(application)
    register_stats_handlers(application)
    register_callback_handlers(application)
    register_message_handlers(application)

    return application


def get_webhook_url() -> str:
    settings = get_settings()

    if settings.webhook_url:
        return settings.webhook_url.rstrip("/")

    render_external_url = os.getenv(
        "RENDER_EXTERNAL_URL",
        "",
    ).strip()

    if render_external_url:
        return (
            render_external_url.rstrip("/")
            + "/telegram/webhook"
        )

    raise RuntimeError(
        "WEBHOOK_URL is not configured and "
        "RENDER_EXTERNAL_URL is unavailable."
    )


async def startup() -> None:
    global telegram_application

    settings = get_settings()

    setup_logging(settings.log_level)

    logger.info(
        "Starting Telegram AI Moderator webhook service..."
    )

    telegram_application = build_application()

    await telegram_application.initialize()

    await post_init(telegram_application)

    await telegram_application.start()

    webhook_url = get_webhook_url()

    await telegram_application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=[
            "message",
            "callback_query",
        ],
        drop_pending_updates=True,
    )

    logger.info(
        "Telegram webhook configured successfully."
    )


async def shutdown() -> None:
    global telegram_application

    if telegram_application is None:
        return

    try:
        await telegram_application.bot.delete_webhook()
    except Exception:
        logger.exception(
            "Failed to delete Telegram webhook."
        )

    try:
        await telegram_application.stop()
    except Exception:
        logger.exception(
            "Failed to stop Telegram application."
        )

    try:
        await post_shutdown(
            telegram_application
        )
    except Exception:
        logger.exception(
            "Failed during application shutdown."
        )

    try:
        await telegram_application.shutdown()
    except Exception:
        logger.exception(
            "Failed to shutdown Telegram application."
        )

    telegram_application = None


async def health_check(
    request: Request,
) -> PlainTextResponse:
    return PlainTextResponse("OK")


async def telegram_webhook(
    request: Request,
) -> PlainTextResponse:
    global telegram_application

    if telegram_application is None:
        return PlainTextResponse(
            "Bot is not ready.",
            status_code=503,
        )

    try:
        data = await request.json()

        update = Update.de_json(
            data,
            telegram_application.bot,
        )

        if update is None:
            return PlainTextResponse(
                "Invalid update.",
                status_code=400,
            )

        await telegram_application.process_update(
            update
        )

        return PlainTextResponse("OK")

    except Exception:
        logger.exception(
            "Failed to process Telegram webhook."
        )

        return PlainTextResponse(
            "Internal Server Error.",
            status_code=500,
        )


async def application_lifespan(app):
    await startup()

    yield

    await shutdown()


routes = [
    Route(
        "/health",
        health_check,
        methods=["GET"],
    ),
    Route(
        "/telegram/webhook",
        telegram_webhook,
        methods=["POST"],
    ),
]


web_app = Starlette(
    routes=routes,
    lifespan=application_lifespan,
)


def run() -> None:
    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=port,
    )

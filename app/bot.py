import asyncio
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
from app.services.moderation import _recent_messages
from app.utils.cleanup import cleanup_old_messages

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
        BotCommand("notifications", "Непрочитанные уведомления"),
        BotCommand("mute", "Замьютить (ответом на сообщение)"),
        BotCommand("unmute", "Снять мут (ответом на сообщение)"),
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
        )

        logger.info("Daily summary job scheduled.")

    if settings.weekly_summary_enabled:
        day_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        day = day_map.get(
            settings.weekly_summary_day.lower(),
            6,
        )

        job_queue.run_daily(
            generate_weekly_summaries,
            time=time(
                hour=settings.weekly_summary_hour,
                minute=0,
            ),
            days=(day,),
        )

        logger.info("Weekly summary job scheduled.")

    job_queue.run_repeating(
        lambda context: cleanup_old_messages(_recent_messages),
        interval=3600,
        first=1,
    )

    logger.info("Memory cleanup job scheduled (every 1 hour).")


async def webhook_handler(request: Request) -> PlainTextResponse:
    """Handle incoming Telegram updates via webhook."""
    if telegram_application is None:
        logger.error("Application not initialized")
        return PlainTextResponse("Application not initialized", status_code=500)

    try:
        data = await request.json()
        update = Update.de_json(data, telegram_application.bot)

        if update is None:
            return PlainTextResponse("Invalid update", status_code=400)

        await telegram_application.process_update(update)

        return PlainTextResponse("ok")

    except Exception as e:
        logger.error(f"Error processing webhook update: {e}", exc_info=True)
        return PlainTextResponse("Internal server error", status_code=500)


async def health_check(request: Request) -> PlainTextResponse:
    """Simple health check endpoint."""
    return PlainTextResponse("ok")


def setup_starlette_app() -> Starlette:
    """Create and configure Starlette application for webhooks."""
    routes = [
        Route("/webhook", webhook_handler, methods=["POST"]),
        Route("/health", health_check, methods=["GET"]),
    ]

    return Starlette(routes=routes)


def run() -> None:
    """Start the Telegram bot."""
    global telegram_application

    settings = get_settings()

    setup_logging(settings.log_level)

    logger.info("Starting Telegram bot...")

    application = ApplicationBuilder().token(
        settings.bot_token,
    ).post_init(
        post_init,
    ).build()

    telegram_application = application

    register_command_handlers(application)
    register_message_handlers(application)
    register_stats_handlers(application)
    register_admin_handlers(application)
    register_callback_handlers(application)

    if settings.webhook_url:
        logger.info(f"Starting bot with webhook: {settings.webhook_url}")

        starlette_app = setup_starlette_app()

        webhook_port = int(os.getenv("PORT", 8000))

        import uvicorn

        config = uvicorn.Config(
            app=starlette_app,
            host="0.0.0.0",
            port=webhook_port,
            log_level=settings.log_level.lower(),
        )

        server = uvicorn.Server(config)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(
                application.initialize()
            )

            logger.info("Bot initialized, setting webhook...")

            loop.run_until_complete(
                application.bot.set_webhook(
                    url=settings.webhook_url,
                    allowed_updates=["message", "callback_query"],
                )
            )

            logger.info(f"Webhook set to: {settings.webhook_url}")

            loop.run_until_complete(server.serve())

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")

        finally:
            loop.run_until_complete(
                application.bot.delete_webhook()
            )

            loop.run_until_complete(
                application.shutdown()
            )

            loop.close()

    else:
        logger.info("Starting bot with polling...")

        application.run_polling(
            allowed_updates=["message", "callback_query"],
        )

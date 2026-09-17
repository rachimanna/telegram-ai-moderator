import asyncio
import logging
import os
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
from app.utils.cleanup import cleanup_job

logger = logging.getLogger(__name__)

telegram_application: Application | None = None

# Path of the Starlette route that receives Telegram webhook updates.
WEBHOOK_PATH = "/telegram/webhook"

# Values that mean "yes, use webhook mode, but figure out the actual public
# URL from the hosting platform" rather than "this is the literal base URL".
_WEBHOOK_URL_PLACEHOLDER_VALUES = {"true", "1", "yes", "on"}


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


def get_scheduler_timezone(settings) -> ZoneInfo:
    """Resolve the ZoneInfo used to schedule daily/weekly summary jobs.

    Falls back to UTC if `TIMEZONE` is missing, empty, or invalid, so a typo
    in the environment never prevents the bot from starting.
    """
    try:
        return ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "Invalid TIMEZONE=%r, falling back to UTC for scheduled jobs.",
            settings.timezone,
        )
        return ZoneInfo("UTC")


async def schedule_jobs(application: Application) -> None:
    """Register periodic JobQueue tasks: daily/weekly summaries and memory cleanup.

    Must be called after `Application.initialize()` but the jobs themselves
    only actually start running once `Application.start()` is awaited.
    """
    job_queue = application.job_queue

    if job_queue is None:
        logger.warning(
            "Job queue is unavailable (is `python-telegram-bot[job-queue]` "
            "installed?). Summaries and memory cleanup will not run."
        )
        return

    settings = get_settings()
    tzinfo = get_scheduler_timezone(settings)

    if settings.daily_summary_enabled:
        job_queue.run_daily(
            generate_daily_summaries,
            time=time(
                hour=settings.daily_summary_hour,
                minute=0,
                tzinfo=tzinfo,
            ),
        )

        logger.info(
            "Daily summary job scheduled at %02d:00 (%s).",
            settings.daily_summary_hour,
            settings.timezone,
        )

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
                tzinfo=tzinfo,
            ),
            days=(day,),
        )

        logger.info(
            "Weekly summary job scheduled on day=%s at %02d:00 (%s).",
            settings.weekly_summary_day,
            settings.weekly_summary_hour,
            settings.timezone,
        )

    job_queue.run_repeating(
        cleanup_job,
        interval=3600,
        first=60,
    )

    logger.info("Memory cleanup job scheduled (every 1 hour).")


async def post_init(application: Application) -> None:
    """One-time async setup performed right after `Application.initialize()`.

    Note: this bot does NOT use `Application.run_polling()` /
    `run_webhook()` (it needs an HTTP health-check server running even in
    polling mode for Render), so PTB's own `post_init` hook machinery is
    bypassed and this function is instead called explicitly from
    `main_async()`.
    """
    logger.info("Initializing database...")

    await initialize_database()

    logger.info("Database initialized.")

    await setup_bot_commands(application)

    await schedule_jobs(application)


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
    """Simple health check endpoint used by Render (`healthCheckPath`)."""
    return PlainTextResponse("ok")


def setup_starlette_app() -> Starlette:
    """Create and configure the Starlette application.

    This HTTP server is started in BOTH webhook and polling mode: Render's
    free "web service" plan requires the process to bind `$PORT` and answer
    on `healthCheckPath`, even when Telegram updates are being long-polled
    instead of pushed to a webhook. Without it, Render considers the deploy
    failed / the service unhealthy.
    """
    routes = [
        Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
        Route("/health", health_check, methods=["GET"]),
    ]

    return Starlette(routes=routes)


def resolve_webhook_base_url(configured_url: str) -> str | None:
    """Figure out the public base URL to register as the Telegram webhook.

    - If `WEBHOOK_URL` looks like a real URL, it is used as-is (backward
      compatible with existing deployments that already set a full URL).
    - If `WEBHOOK_URL` is just a "please enable webhook mode" placeholder
      (e.g. "true"/"1"/"yes"), or is otherwise unusable, we fall back to
      Render's own `RENDER_EXTERNAL_URL` environment variable, which Render
      injects automatically into every web service — this lets a Render
      deployment enable webhook mode with zero manual URL configuration.
    - Returns None if no usable base URL can be determined at all.
    """
    candidate = (configured_url or "").strip()

    if candidate and candidate.lower() not in _WEBHOOK_URL_PLACEHOLDER_VALUES:
        return candidate.rstrip("/")

    render_external_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()

    if render_external_url:
        return render_external_url.rstrip("/")

    return None


def build_webhook_url(base_url: str) -> str:
    """Append the webhook path to a base URL, without ever duplicating it."""
    base_url = base_url.rstrip("/")

    if base_url.endswith(WEBHOOK_PATH):
        return base_url

    return f"{base_url}{WEBHOOK_PATH}"


async def run_webhook_mode(application: Application) -> None:
    """Configure Telegram to push updates to our Starlette route, then start
    the Application (this starts the JobQueue, among other things).
    """
    settings = get_settings()

    base_url = resolve_webhook_base_url(settings.webhook_url)

    if base_url is None:
        logger.error(
            "WEBHOOK_URL=%r but no usable base URL could be resolved and "
            "RENDER_EXTERNAL_URL is not set either. Falling back to long "
            "polling so the bot keeps working.",
            settings.webhook_url,
        )

        await run_polling_mode(application)

        return

    webhook_url = build_webhook_url(base_url)

    logger.info("Configuring webhook: %s", webhook_url)

    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
    )

    logger.info("Webhook configured. Starting Application (JobQueue, etc.)...")

    await application.start()


async def run_polling_mode(application: Application) -> None:
    """Start long-polling for updates. An HTTP health server is started in
    parallel by the caller so Render's health check still passes.
    """
    logger.info(
        "Starting bot in long-polling mode "
        "(an HTTP health server is started in parallel for Render)."
    )

    await application.updater.start_polling(
        allowed_updates=["message", "callback_query"],
    )

    await application.start()


async def shutdown_bot(application: Application) -> None:
    """Best-effort graceful shutdown: stop polling (if any), stop the
    Application (this stops the JobQueue), then release its resources.
    Each step is isolated so a failure in one does not skip the others.
    """
    logger.info("Shutting down bot...")

    try:
        if application.updater is not None and application.updater.running:
            await application.updater.stop()
    except Exception:
        logger.exception("Error while stopping updater.")

    try:
        if application.running:
            await application.stop()
    except Exception:
        logger.exception("Error while stopping application.")

    try:
        await application.shutdown()
    except Exception:
        logger.exception("Error while shutting down application.")

    logger.info("Bot shut down cleanly.")


async def main_async() -> None:
    global telegram_application

    settings = get_settings()

    setup_logging(settings.log_level)

    logger.info("Starting Telegram bot...")

    application = ApplicationBuilder().token(
        settings.bot_token,
    ).build()

    telegram_application = application

    register_command_handlers(application)
    register_message_handlers(application)
    register_stats_handlers(application)
    register_admin_handlers(application)
    register_callback_handlers(application)

    starlette_app = setup_starlette_app()

    port = int(os.getenv("PORT", 8000))

    import uvicorn

    uvicorn_config = uvicorn.Config(
        app=starlette_app,
        host="0.0.0.0",
        port=port,
        log_level=settings.log_level.lower(),
    )

    server = uvicorn.Server(uvicorn_config)

    await application.initialize()

    logger.info("Application initialized.")

    await post_init(application)

    try:
        if settings.webhook_url:
            await run_webhook_mode(application)
        else:
            await run_polling_mode(application)

        logger.info("Starting HTTP server on 0.0.0.0:%s ...", port)

        # `server.serve()` installs its own SIGINT/SIGTERM handlers and
        # returns cleanly once one of them fires, which lets the `finally`
        # block below perform a graceful shutdown of the Telegram side.
        await server.serve()

    finally:
        await shutdown_bot(application)


def run() -> None:
    """Start the Telegram bot. Entry point used by `python -m app`.

    Both webhook and long-polling modes run inside the same asyncio event
    loop together with the Starlette/uvicorn HTTP server, so the JobQueue
    (daily/weekly summaries, memory cleanup) and the `/health` endpoint
    required by Render both work regardless of the chosen mode.
    """
    asyncio.run(main_async())

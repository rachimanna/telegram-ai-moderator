import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

from app.db.models import Group
from app.db.session import SessionLocal
from app.services.settings import (
    get_or_create_group,
    get_or_create_settings,
    update_settings,
)

logger = logging.getLogger(__name__)


async def is_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    chat = update.effective_chat
    user = update.effective_user

    if chat is None or user is None:
        return False

    try:
        member = await context.bot.get_chat_member(
            chat.id,
            user.id,
        )
    except Exception:
        logger.exception(
            "Failed to check admin status."
        )
        return False

    return member.status in {
        "administrator",
        "creator",
    }


def settings_keyboard(
    moderation_enabled: bool,
    ai_answers_enabled: bool,
    strictness: str,
    warning_threshold: int,
    daily_summary_enabled: bool,
    weekly_summary_enabled: bool,
) -> InlineKeyboardMarkup:
    moderation_text = (
        "🛡 Модерация: ВКЛ"
        if moderation_enabled
        else "🛡 Модерация: ВЫКЛ"
    )

    ai_text = (
        "🤖 AI-ответы: ВКЛ"
        if ai_answers_enabled
        else "🤖 AI-ответы: ВЫКЛ"
    )

    daily_text = (
        "📋 Ежедневная сводка: ВКЛ"
        if daily_summary_enabled
        else "📋 Ежедневная сводка: ВЫКЛ"
    )

    weekly_text = (
        "📊 Еженедельная сводка: ВКЛ"
        if weekly_summary_enabled
        else "📊 Еженедельная сводка: ВЫКЛ"
    )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    moderation_text,
                    callback_data="admin_moderation",
                )
            ],
            [
                InlineKeyboardButton(
                    ai_text,
                    callback_data="admin_ai",
                )
            ],
            [
                InlineKeyboardButton(
                    f"🎚 Строгость: {strictness}",
                    callback_data="admin_strictness",
                )
            ],
            [
                InlineKeyboardButton(
                    f"⚠️ Лимит: {warning_threshold}",
                    callback_data="admin_threshold",
                )
            ],
            [
                InlineKeyboardButton(
                    daily_text,
                    callback_data="admin_daily",
                )
            ],
            [
                InlineKeyboardButton(
                    weekly_text,
                    callback_data="admin_weekly",
                )
            ],
        ]
    )


async def build_settings_message(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
):
    async with SessionLocal() as session:
        group = await get_or_create_group(
            session,
            telegram_group_id=chat_id,
            title="Telegram Group",
        )

        settings = await get_or_create_settings(
            session,
            group,
        )

        await session.commit()

        text = (
            "⚙️ Настройки AI-модератора\n\n"
            f"🛡 Модерация: "
            f"{'ВКЛ' if settings.moderation_enabled else 'ВЫКЛ'}\n"
            f"🤖 AI-ответы: "
            f"{'ВКЛ' if settings.ai_answers_enabled else 'ВЫКЛ'}\n"
            f"🎚 Строгость: {settings.strictness}\n"
            f"⚠️ Лимит предупреждений: "
            f"{settings.warning_threshold}\n"
            f"📋 Ежедневная сводка: "
            f"{'ВКЛ' if settings.daily_summary_enabled else 'ВЫКЛ'}\n"
            f"📊 Еженедельная сводка: "
            f"{'ВКЛ' if settings.weekly_summary_enabled else 'ВЫКЛ'}"
        )

        keyboard = settings_keyboard(
            moderation_enabled=settings.moderation_enabled,
            ai_answers_enabled=settings.ai_answers_enabled,
            strictness=settings.strictness,
            warning_threshold=settings.warning_threshold,
            daily_summary_enabled=settings.daily_summary_enabled,
            weekly_summary_enabled=settings.weekly_summary_enabled,
        )

        return text, keyboard


async def settings_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.effective_message is None:
        return

    if not await is_admin(
        update,
        context,
    ):
        await update.effective_message.reply_text(
            "⛔ Только администраторы группы "
            "могут изменять настройки."
        )
        return

    chat = update.effective_chat

    if chat is None:
        return

    text, keyboard = await build_settings_message(
        chat.id,
        context,
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=keyboard,
    )


async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query

    if query is None:
        return

    if not await is_admin(
        update,
        context,
    ):
        await query.answer(
            "⛔ Только для администраторов.",
            show_alert=True,
        )
        return

    chat = update.effective_chat

    if chat is None:
        return

    data = query.data or ""

    async with SessionLocal() as session:
        group = await get_or_create_group(
            session,
            telegram_group_id=chat.id,
            title=chat.title or "Telegram Group",
        )

        settings = await get_or_create_settings(
            session,
            group,
        )

        # ---------------------------------------------
        # Toggle moderation
        # ---------------------------------------------

        if data == "admin_moderation":
            await update_settings(
                session,
                group,
                moderation_enabled=(
                    not settings.moderation_enabled
                ),
            )

        # ---------------------------------------------
        # Toggle AI answers
        # ---------------------------------------------

        elif data == "admin_ai":
            await update_settings(
                session,
                group,
                ai_answers_enabled=(
                    not settings.ai_answers_enabled
                ),
            )

        # ---------------------------------------------
        # Strictness
        # ---------------------------------------------

        elif data == "admin_strictness":
            values = [
                "low",
                "medium",
                "high",
            ]

            current = settings.strictness

            try:
                index = values.index(current)
            except ValueError:
                index = 1

            next_value = values[
                (index + 1) % len(values)
            ]

            await update_settings(
                session,
                group,
                strictness=next_value,
            )

        # ---------------------------------------------
        # Warning threshold
        # ---------------------------------------------

        elif data == "admin_threshold":
            values = [
                2,
                3,
                5,
                10,
            ]

            current = settings.warning_threshold

            try:
                index = values.index(current)
            except ValueError:
                index = 1

            next_value = values[
                (index + 1) % len(values)
            ]

            await update_settings(
                session,
                group,
                warning_threshold=next_value,
            )

        # ---------------------------------------------
        # Daily summary
        # ---------------------------------------------

        elif data == "admin_daily":
            await update_settings(
                session,
                group,
                daily_summary_enabled=(
                    not settings.daily_summary_enabled
                ),
            )

        # ---------------------------------------------
        # Weekly summary
        # ---------------------------------------------

        elif data == "admin_weekly":
            await update_settings(
                session,
                group,
                weekly_summary_enabled=(
                    not settings.weekly_summary_enabled
                ),
            )

        await session.commit()

    text, keyboard = await build_settings_message(
        chat.id,
        context,
    )

    try:
        await query.answer(
            "Настройка изменена."
        )

        await query.edit_message_text(
            text,
            reply_markup=keyboard,
        )

    except Exception:
        logger.exception(
            "Failed to update admin settings message."
        )


def register_admin_handlers(
    application,
) -> None:
    application.add_handler(
        CommandHandler(
            "settings",
            settings_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin_",
        )
    )

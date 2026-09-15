from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.openai_compatible import create_ai_provider
from app.ai.prompts import build_assistant_prompt
from app.config import get_settings
from app.db.models import Message


async def get_recent_context(
    session: AsyncSession,
    group_id: int,
    limit: int | None = None,
) -> str:
    settings = get_settings()

    context_limit = (
        limit
        if limit is not None
        else settings.max_context_messages
    )

    context_limit = max(
        1,
        min(context_limit, 500),
    )

    result = await session.execute(
        select(Message)
        .where(
            Message.group_id == group_id,
            Message.is_deleted.is_(False),
        )
        .order_by(
            Message.created_at.desc()
        )
        .limit(context_limit)
    )

    messages = list(
        result.scalars().all()
    )

    messages.reverse()

    if not messages:
        return (
            "В группе пока нет сохранённой "
            "истории сообщений."
        )

    lines: list[str] = []

    for message in messages:
        text = message.text.strip()

        if not text:
            continue

        if len(text) > settings.max_message_length:
            text = (
                text[
                    :settings.max_message_length
                ]
                + "..."
            )

        timestamp = message.created_at.strftime(
            "%Y-%m-%d %H:%M"
        )

        user_label = (
            str(message.user_id)
            if message.user_id is not None
            else "unknown"
        )

        lines.append(
            f"[{timestamp}] "
            f"user_id={user_label}: "
            f"{text}"
        )

    if not lines:
        return (
            "В группе пока нет текстовых "
            "сообщений."
        )

    return "\n".join(lines)


async def get_today_context(
    session: AsyncSession,
    group_id: int,
) -> str:
    now = datetime.utcnow()

    start_of_day = datetime(
        year=now.year,
        month=now.month,
        day=now.day,
    )

    result = await session.execute(
        select(Message)
        .where(
            Message.group_id == group_id,
            Message.created_at >= start_of_day,
            Message.is_deleted.is_(False),
        )
        .order_by(
            Message.created_at.asc()
        )
    )

    messages = list(
        result.scalars().all()
    )

    if not messages:
        return (
            "Сегодня в группе ещё нет "
            "сохранённых сообщений."
        )

    settings = get_settings()

    lines: list[str] = []

    for message in messages:
        text = message.text.strip()

        if not text:
            continue

        if len(text) > settings.max_message_length:
            text = (
                text[
                    :settings.max_message_length
                ]
                + "..."
            )

        timestamp = message.created_at.strftime(
            "%H:%M"
        )

        user_label = (
            str(message.user_id)
            if message.user_id is not None
            else "unknown"
        )

        lines.append(
            f"[{timestamp}] "
            f"user_id={user_label}: "
            f"{text}"
        )

    if not lines:
        return (
            "Сегодня нет текстовых сообщений."
        )

    return "\n".join(lines)


def normalize_question(
    question: str,
) -> str:
    question = question.strip()

    if not question:
        return ""

    if len(question) > 4000:
        question = question[:4000]

    return question


async def generate_ai_answer(
    context: str,
    question: str,
) -> str:
    provider = create_ai_provider()

    messages = build_assistant_prompt(
        context=context,
        question=question,
    )

    answer = await provider.generate(
        messages,
        temperature=0.2,
        max_tokens=1200,
    )

    answer = answer.strip()

    if not answer:
        return (
            "ИИ не смог сформировать ответ. "
            "Попробуйте повторить вопрос."
        )

    return answer


async def answer_question(
    session: AsyncSession,
    group_id: int,
    question: str,
) -> str:
    question = normalize_question(
        question
    )

    if not question:
        return (
            "Пожалуйста, напишите вопрос."
        )

    context = await get_recent_context(
        session,
        group_id,
    )

    return await generate_ai_answer(
        context=context,
        question=question,
    )


async def answer_today_question(
    session: AsyncSession,
    group_id: int,
    question: str,
) -> str:
    question = normalize_question(
        question
    )

    if not question:
        question = (
            "Сделай краткий обзор того, "
            "что сегодня обсуждали в группе."
        )

    context = await get_today_context(
        session,
        group_id,
    )

    return await generate_ai_answer(
        context=context,
        question=question,
    )

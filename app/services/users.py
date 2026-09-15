from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    display_name: str,
) -> User:
    result = await session.execute(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
        )

        session.add(user)

        await session.flush()

        return user

    user.username = username

    if display_name.strip():
        user.display_name = (
            display_name.strip()
        )

    await session.flush()

    return user

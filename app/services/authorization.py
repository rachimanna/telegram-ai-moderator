from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


ROLE_USER = "user"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"
ROLE_OWNER = "owner"


ROLE_LEVELS = {
    ROLE_USER: 0,
    ROLE_MODERATOR: 1,
    ROLE_ADMIN: 2,
    ROLE_OWNER: 3,
}


def normalize_role(
    role: str | None,
) -> str:
    if not role:
        return ROLE_USER

    role = role.lower().strip()

    if role not in ROLE_LEVELS:
        return ROLE_USER

    return role


def has_role(
    user_role: str | None,
    required_role: str,
) -> bool:
    current = normalize_role(
        user_role
    )

    required = normalize_role(
        required_role
    )

    return (
        ROLE_LEVELS[current]
        >= ROLE_LEVELS[required]
    )


def is_moderator(
    user_role: str | None,
) -> bool:
    return has_role(
        user_role,
        ROLE_MODERATOR,
    )


def is_admin(
    user_role: str | None,
) -> bool:
    return has_role(
        user_role,
        ROLE_ADMIN,
    )


def is_owner(
    user_role: str | None,
) -> bool:
    return has_role(
        user_role,
        ROLE_OWNER,
    )


async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
) -> User | None:
    result = await session.execute(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    return result.scalar_one_or_none()


async def get_user_role(
    session: AsyncSession,
    telegram_id: int,
) -> str:
    user = await get_user_by_telegram_id(
        session,
        telegram_id,
    )

    if user is None:
        return ROLE_USER

    return normalize_role(
        getattr(user, "role", None)
    )


async def set_user_role(
    session: AsyncSession,
    telegram_id: int,
    role: str,
) -> User:
    role = normalize_role(role)

    user = await get_user_by_telegram_id(
        session,
        telegram_id,
    )

    if user is None:
        raise ValueError(
            "Пользователь не найден."
        )

    user.role = role

    await session.flush()

    return user


async def require_role(
    session: AsyncSession,
    telegram_id: int,
    required_role: str,
) -> bool:
    role = await get_user_role(
        session,
        telegram_id,
    )

    return has_role(
        role,
        required_role,
    )

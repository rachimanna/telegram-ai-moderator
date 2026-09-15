from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupRole


class RoleLevel(IntEnum):
    USER = 0
    MODERATOR = 1
    ADMIN = 2
    OWNER = 3


ROLE_LEVELS = {
    "user": RoleLevel.USER,
    "moderator": RoleLevel.MODERATOR,
    "admin": RoleLevel.ADMIN,
    "owner": RoleLevel.OWNER,
}


def normalize_role(role: str | None) -> str:
    if not role:
        return "user"

    role = role.lower().strip()

    if role not in ROLE_LEVELS:
        return "user"

    return role


async def get_stored_role(
    session: AsyncSession,
    group_id: int,
    user_id: int,
) -> str:
    result = await session.execute(
        select(GroupRole.role).where(
            GroupRole.group_id == group_id,
            GroupRole.user_id == user_id,
        )
    )

    role = result.scalar_one_or_none()

    return normalize_role(role)


def has_permission(
    current_role: str,
    required_role: str,
) -> bool:
    current = ROLE_LEVELS.get(
        normalize_role(current_role),
        RoleLevel.USER,
    )

    required = ROLE_LEVELS.get(
        normalize_role(required_role),
        RoleLevel.USER,
    )

    return current >= required


def can_moderate(role: str) -> bool:
    return has_permission(role, "moderator")


def can_manage_settings(role: str) -> bool:
    return has_permission(role, "admin")


def can_manage_roles(role: str) -> bool:
    return has_permission(role, "owner")

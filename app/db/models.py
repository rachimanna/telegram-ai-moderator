from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )
    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        default="Unknown",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        default="Telegram Group",
    )
    settings: Mapped["GroupSettings | None"] = relationship(
        back_populates="group",
        uselist=False,
        cascade="all, delete-orphan",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


class GroupSettings(Base):
    __tablename__ = "group_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        unique=True,
    )

    moderation_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    ai_answers_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    strictness: Mapped[str] = mapped_column(
        String(20),
        default="medium",
    )
    moderation_action: Mapped[str] = mapped_column(
        String(30),
        default="warn",
    )
    warning_threshold: Mapped[int] = mapped_column(
        Integer,
        default=3,
    )

    daily_summary_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    weekly_summary_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    excluded_user_ids: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
    )
    excluded_words: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
    )

    group: Mapped[Group] = relationship(
        back_populates="settings",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "telegram_message_id",
            name="uq_group_message",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    telegram_message_id: Mapped[int] = mapped_column(
        BigInteger,
    )

    text: Mapped[str] = mapped_column(
        Text,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )


class Warning(Base):
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
    )

    severity: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )


class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    action: Mapped[str] = mapped_column(
        String(50),
    )
    reason: Mapped[str] = mapped_column(
        Text,
        default="",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        default="unknown",
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )


class GroupStat(Base):
    __tablename__ = "group_stats"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "day",
            name="uq_group_stat_day",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )

    day: Mapped[date] = mapped_column(
        Date,
        index=True,
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    active_users: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    violations: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    deleted_messages: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    questions: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )


class GroupRole(Base):
    __tablename__ = "group_roles"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "user_id",
            name="uq_group_user_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        default="user",
    )


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )

    summary_type: Mapped[str] = mapped_column(
        String(30),
    )

    content: Mapped[str] = mapped_column(
        Text,
    )

    period_start: Mapped[datetime] = mapped_column(
        DateTime,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

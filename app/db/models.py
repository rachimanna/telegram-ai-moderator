from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="user",
        server_default="user",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    messages = relationship(
        "Message",
        back_populates="user",
    )

    warnings = relationship(
        "Warning",
        back_populates="user",
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    settings = relationship(
        "GroupSettings",
        back_populates="group",
        uselist=False,
    )

    messages = relationship(
        "Message",
        back_populates="group",
    )

    warnings = relationship(
        "Warning",
        back_populates="group",
    )

    moderation_logs = relationship(
        "ModerationLog",
        back_populates="group",
    )

    statistics = relationship(
        "GroupStat",
        back_populates="group",
    )

    summaries = relationship(
        "Summary",
        back_populates="group",
    )


class GroupSettings(Base):
    __tablename__ = "group_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        unique=True,
        nullable=False,
    )

    moderation_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    ai_answers_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    strictness: Mapped[str] = mapped_column(
        String(32),
        default="medium",
        nullable=False,
    )

    moderation_action: Mapped[str] = mapped_column(
        String(32),
        default="warn",
        nullable=False,
    )

    warning_threshold: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    daily_summary_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    weekly_summary_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    excluded_user_ids: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    excluded_words: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    group = relationship(
        "Group",
        back_populates="settings",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    telegram_message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    group = relationship(
        "Group",
        back_populates="messages",
    )

    user = relationship(
        "User",
        back_populates="messages",
    )

    moderation_logs = relationship(
        "ModerationLog",
        back_populates="message",
    )


class Warning(Base):
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    group = relationship(
        "Group",
        back_populates="warnings",
    )

    user = relationship(
        "User",
        back_populates="warnings",
    )


class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"),
        nullable=True,
    )

    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    category: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    group = relationship(
        "Group",
        back_populates="moderation_logs",
    )

    message = relationship(
        "Message",
        back_populates="moderation_logs",
    )


class GroupStat(Base):
    __tablename__ = "group_stats"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )

    day: Mapped[datetime] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    active_users: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    violations: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    deleted_messages: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    questions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    group = relationship(
        "Group",
        back_populates="statistics",
    )

    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "day",
            name="uq_group_stats_group_day",
        ),
    )


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )

    summary_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    period_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    period_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    group = relationship(
        "Group",
        back_populates="summaries",
    )

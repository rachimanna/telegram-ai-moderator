from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")

    database_url: str = Field(alias="DATABASE_URL")

    ai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="AI_BASE_URL",
    )
    ai_api_key: str = Field(default="", alias="AI_API_KEY")
    ai_model: str = Field(default="", alias="AI_MODEL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    timezone: str = Field(default="Europe/Berlin", alias="TIMEZONE")

    default_moderation_enabled: bool = Field(
        default=True,
        alias="DEFAULT_MODERATION_ENABLED",
    )
    default_ai_answers_enabled: bool = Field(
        default=True,
        alias="DEFAULT_AI_ANSWERS_ENABLED",
    )
    default_strictness: str = Field(
        default="medium",
        alias="DEFAULT_STRICTNESS",
    )
    default_moderation_action: str = Field(
        default="warn",
        alias="DEFAULT_MODERATION_ACTION",
    )
    default_warning_threshold: int = Field(
        default=3,
        alias="DEFAULT_WARNING_THRESHOLD",
    )

    max_context_messages: int = Field(
        default=100,
        alias="MAX_CONTEXT_MESSAGES",
    )
    max_message_length: int = Field(
        default=4000,
        alias="MAX_MESSAGE_LENGTH",
    )
    ai_timeout_seconds: int = Field(
        default=30,
        alias="AI_TIMEOUT_SECONDS",
    )

    daily_summary_enabled: bool = Field(
        default=True,
        alias="DAILY_SUMMARY_ENABLED",
    )
    weekly_summary_enabled: bool = Field(
        default=True,
        alias="WEEKLY_SUMMARY_ENABLED",
    )
    daily_summary_hour: int = Field(
        default=21,
        alias="DAILY_SUMMARY_HOUR",
    )
    weekly_summary_day: str = Field(
        default="sunday",
        alias="WEEKLY_SUMMARY_DAY",
    )
    weekly_summary_hour: int = Field(
        default=20,
        alias="WEEKLY_SUMMARY_HOUR",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

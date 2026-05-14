from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    admin_ids: list[int]
    remnawave_base_url: str
    remnawave_token: str
    database_url: str
    poll_interval_seconds: int = 120
    escalation_window_minutes: int = 60
    escalation_max_attempts: int = 3

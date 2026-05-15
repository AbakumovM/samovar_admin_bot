from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    admin_ids: list[int]

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return list(v)  # type: ignore[arg-type]
    remnawave_base_url: str
    remnawave_token: str
    database_url: str
    poll_interval_seconds: int = 120
    fast_poll_interval_seconds: int = 30
    escalation_window_minutes: int = 60
    escalation_max_attempts: int = 3
    daily_report_hour_utc: int = 17  # 20:00 MSK
    traffic_check_interval_seconds: int = 3600
    traffic_anomaly_threshold_gb: float = 50.0
    traffic_anomaly_multiplier: float = 3.0

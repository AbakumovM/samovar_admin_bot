import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_str_list(v: object) -> list[str]:
    if isinstance(v, str):
        # Try JSON first
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            # Fall back to comma-separated
            return [x.strip() for x in v.split(",") if x.strip()]
    if v is None:
        return []
    return list(v)  # type: ignore[arg-type]


def _parse_int_list(v: object) -> list[int]:
    if isinstance(v, str):
        return [int(x.strip()) for x in v.split(",") if x.strip()]
    if isinstance(v, int):
        return [v]
    if v is None:
        return []
    return list(v)  # type: ignore[arg-type]


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
    traffic_anomaly_threshold_gb: float = 30.0
    traffic_anomaly_multiplier: float = 2.0
    billing_currency: str = "$"
    billing_alert_days_before: int = 3
    billing_check_hour_utc: int = 17
    antifraud_enabled: bool = False
    antifraud_scan_interval_seconds: int = 1800
    antifraud_ip_slack: int = 2
    antifraud_ip_slack_multiplier: float = 0.0
    antifraud_ip_recency_seconds: int = 60
    antifraud_cooldown_hours: int = 24
    antifraud_job_poll_interval_seconds: float = 1.0
    antifraud_job_poll_timeout_seconds: float = 15.0
    antifraud_user_cache_ttl_seconds: float = 300.0
    antifraud_user_resolve_concurrency: int = 8
    antifraud_ignored_node_uuids: list[str] = []
    antifraud_ip_whitelist: list[str] = []
    antifraud_whitelist_user_ids: list[int] = []
    antifraud_soft_alerts_enabled: bool = False
    antifraud_violation_threshold: int = 1
    antifraud_violation_window_seconds: int = 3600
    antifraud_subnet_grouping: bool = False
    antifraud_subnet_prefix_v4: int = 24
    antifraud_asn_grouping: bool = False
    antifraud_maxmind_account_id: str = ""
    antifraud_maxmind_license_key: str = ""
    antifraud_asn_database_path: str = "./geoip/GeoLite2-ASN.mmdb"
    antifraud_maxmind_update_interval_hours: int = 168
    antifraud_auto_block_enabled: bool = False
    antifraud_ru_node_prefixes: list[str] = ["RU"]
    antifraud_ru_node_ip_threshold: int = 2
    samovarbot_base_url: str = ""
    samovarbot_internal_api_key: str = ""

    @field_validator(
        "antifraud_ignored_node_uuids",
        "antifraud_ip_whitelist",
        "antifraud_ru_node_prefixes",
        mode="before",
    )
    @classmethod
    def parse_antifraud_str_lists(cls, v: object) -> list[str]:
        return _parse_str_list(v)

    @field_validator("antifraud_whitelist_user_ids", mode="before")
    @classmethod
    def parse_antifraud_whitelist_user_ids(cls, v: object) -> list[int]:
        return _parse_int_list(v)

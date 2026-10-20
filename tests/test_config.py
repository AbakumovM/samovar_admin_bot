
from src.config import Config


def _base_kwargs() -> dict[str, object]:
    return {
        "telegram_bot_token": "x",
        "admin_ids": [1],
        "remnawave_base_url": "https://x",
        "remnawave_token": "x",
        "database_url": "postgresql+asyncpg://a:b@c/d",
    }


def test_antifraud_autoblock_defaults() -> None:
    config = Config(_env_file=None, **_base_kwargs())  # type: ignore[call-arg,arg-type]
    assert config.antifraud_auto_block_enabled is False
    assert config.samovarbot_base_url == ""
    assert config.samovarbot_internal_api_key == ""

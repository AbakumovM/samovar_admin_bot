
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
    assert config.antifraud_ru_node_prefixes == ["RU"]
    assert config.antifraud_ru_node_ip_threshold == 2
    assert config.samovarbot_base_url == ""
    assert config.samovarbot_internal_api_key == ""


def test_antifraud_ru_node_prefixes_parses_json_list() -> None:
    config = Config(  # type: ignore[call-arg]
        _env_file=None,
        antifraud_ru_node_prefixes='["RU", "MOW"]',  # type: ignore[arg-type]
        **_base_kwargs(),  # type: ignore[arg-type]
    )
    assert config.antifraud_ru_node_prefixes == ["RU", "MOW"]

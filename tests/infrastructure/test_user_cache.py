from unittest.mock import patch

from src.infrastructure.remnawave.user_cache import UserLookupCache


def test_get_returns_none_when_missing() -> None:
    cache = UserLookupCache(ttl_seconds=60)
    assert cache.get(1) is None


def test_set_then_get_returns_stored_record() -> None:
    cache = UserLookupCache(ttl_seconds=60)
    record = {"id": 1, "username": "u1"}
    cache.set(1, record)
    assert cache.get(1) == record


def test_get_returns_none_after_ttl_expires() -> None:
    cache = UserLookupCache(ttl_seconds=10)
    with patch("src.infrastructure.remnawave.user_cache.time.monotonic", return_value=1000.0):
        cache.set(1, {"id": 1})
    with patch("src.infrastructure.remnawave.user_cache.time.monotonic", return_value=1011.0):
        assert cache.get(1) is None


def test_get_within_ttl_still_returns_record() -> None:
    cache = UserLookupCache(ttl_seconds=10)
    with patch("src.infrastructure.remnawave.user_cache.time.monotonic", return_value=1000.0):
        cache.set(1, {"id": 1})
    with patch("src.infrastructure.remnawave.user_cache.time.monotonic", return_value=1005.0):
        assert cache.get(1) == {"id": 1}

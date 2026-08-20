import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.apps.antifraud.controllers.scheduler.tasks import _resolve_users_bounded
from src.infrastructure.remnawave.user_cache import UserLookupCache


def _response(status_code: int, body: dict | None = None) -> MagicMock:  # type: ignore[type-arg]
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if body is not None:
        response.json = MagicMock(return_value={"response": body})
    return response


async def test_resolve_users_bounded_resolves_all_ids() -> None:
    raw_client = MagicMock()
    raw_client.get = AsyncMock(
        side_effect=lambda url: _response(200, {"id": int(url.split("/")[-1]), "username": "u"})
    )
    cache = UserLookupCache(ttl_seconds=60)

    result = await _resolve_users_bounded(raw_client, cache, [1, 2, 3], concurrency=8)

    assert set(result.keys()) == {1, 2, 3}


async def test_resolve_users_bounded_skips_404s() -> None:
    async def fake_get(url: str) -> MagicMock:
        uid = int(url.split("/")[-1])
        if uid == 2:
            return _response(404)
        return _response(200, {"id": uid, "username": "u"})

    raw_client = MagicMock()
    raw_client.get = AsyncMock(side_effect=fake_get)
    cache = UserLookupCache(ttl_seconds=60)

    result = await _resolve_users_bounded(raw_client, cache, [1, 2, 3], concurrency=8)

    assert set(result.keys()) == {1, 3}


async def test_resolve_users_bounded_respects_concurrency_limit() -> None:
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def fake_get(url: str) -> MagicMock:
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        uid = int(url.split("/")[-1])
        return _response(200, {"id": uid, "username": "u"})

    raw_client = MagicMock()
    raw_client.get = AsyncMock(side_effect=fake_get)
    cache = UserLookupCache(ttl_seconds=60)

    await _resolve_users_bounded(raw_client, cache, list(range(20)), concurrency=3)

    assert max_in_flight <= 3


async def test_resolve_users_bounded_uses_cache_without_http_call() -> None:
    raw_client = MagicMock()
    raw_client.get = AsyncMock(return_value=_response(200, {"id": 1, "username": "cached"}))
    cache = UserLookupCache(ttl_seconds=60)
    cache.set(1, {"id": 1, "username": "from_cache"})

    result = await _resolve_users_bounded(raw_client, cache, [1], concurrency=8)

    assert result[1]["username"] == "from_cache"
    raw_client.get.assert_not_awaited()

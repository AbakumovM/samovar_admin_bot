from unittest.mock import AsyncMock, MagicMock

import httpx

from src.infrastructure.samovarbot.client import block_user, check_no_active_payment


def _response(status_code: int, body: dict | None = None) -> MagicMock:  # type: ignore[type-arg]
    response = MagicMock()
    response.status_code = status_code
    if body is not None:
        response.json = MagicMock(return_value=body)
    return response


async def test_check_no_active_payment_true_when_inactive() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=_response(200, {"has_active_subscription": False}))

    result = await check_no_active_payment(client, 999)

    assert result is True
    client.get.assert_awaited_once_with("/internal/users/999/payment-status")


async def test_check_no_active_payment_false_when_active() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=_response(200, {"has_active_subscription": True}))

    result = await check_no_active_payment(client, 999)

    assert result is False


async def test_check_no_active_payment_none_on_404() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=_response(404))

    result = await check_no_active_payment(client, 999)

    assert result is None


async def test_check_no_active_payment_none_on_network_error() -> None:
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await check_no_active_payment(client, 999)

    assert result is None


async def test_check_no_active_payment_none_on_missing_key() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=_response(200, {}))

    result = await check_no_active_payment(client, 999)

    assert result is None


async def test_check_no_active_payment_none_on_invalid_json() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(side_effect=ValueError("not json"))
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    result = await check_no_active_payment(client, 999)

    assert result is None


async def test_block_user_true_on_200() -> None:
    client = MagicMock()
    client.post = AsyncMock(return_value=_response(200, {"blocked": True}))

    result = await block_user(client, 999, "antifraud: 3/3")

    assert result is True
    client.post.assert_awaited_once_with(
        "/internal/users/999/block", json={"reason": "antifraud: 3/3"}
    )


async def test_block_user_false_on_non_200() -> None:
    client = MagicMock()
    client.post = AsyncMock(return_value=_response(401))

    result = await block_user(client, 999, "antifraud: 3/3")

    assert result is False


async def test_block_user_false_on_network_error() -> None:
    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await block_user(client, 999, "antifraud: 3/3")

    assert result is False

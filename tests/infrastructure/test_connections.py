from unittest.mock import AsyncMock, MagicMock

import httpx

from src.infrastructure.remnawave.connections import drop_user_connections


async def test_drop_user_connections_posts_payload() -> None:
    raw_client = MagicMock()
    raw_client.post = AsyncMock(return_value=MagicMock())

    result = await drop_user_connections(raw_client, 42)

    assert result is True
    raw_client.post.assert_awaited_once_with(
        "/connections/drop",
        json={
            "dropBy": {"by": "userIds", "userIds": [42]},
            "targetNodes": {"target": "allNodes"},
        },
    )


async def test_drop_user_connections_false_on_error() -> None:
    raw_client = MagicMock()
    raw_client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await drop_user_connections(raw_client, 42)

    assert result is False

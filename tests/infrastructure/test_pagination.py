from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.remnawave.pagination import fetch_all_users_stream


def _response(json_body: dict) -> MagicMock:  # type: ignore[type-arg]
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"response": json_body})
    return response


async def test_fetch_all_users_stream_single_page() -> None:
    raw_client = MagicMock()
    raw_client.get = AsyncMock(
        return_value=_response({
            "users": [{"id": 1, "status": "ACTIVE"}, {"id": 2, "status": "DISABLED"}],
            "hasMore": False,
            "nextCursor": None,
        })
    )

    users = await fetch_all_users_stream(raw_client)

    assert [u["id"] for u in users] == [1, 2]
    raw_client.get.assert_awaited_once_with("/users/stream", params={"size": 1000})


async def test_fetch_all_users_stream_multi_page_follows_cursor() -> None:
    raw_client = MagicMock()
    raw_client.get = AsyncMock(
        side_effect=[
            _response({"users": [{"id": 1}], "hasMore": True, "nextCursor": 5}),
            _response({"users": [{"id": 6}], "hasMore": False, "nextCursor": None}),
        ]
    )

    users = await fetch_all_users_stream(raw_client)

    assert [u["id"] for u in users] == [1, 6]
    second_call_kwargs = raw_client.get.await_args_list[1].kwargs
    assert second_call_kwargs["params"]["cursor"] == 5

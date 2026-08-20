from typing import Any

import httpx


async def fetch_all_users_stream(raw_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Full unfiltered cursor-paginated pass over /users/stream.

    Returns every user record regardless of status/telegramId — callers apply
    their own filters. Kept as shared infra (not owned by one app domain)
    since multiple apps need this same cursor walk and must not duplicate it.
    """
    users: list[dict[str, Any]] = []
    cursor: int | None = None
    size = 1000
    while True:
        params: dict[str, int] = {"size": size}
        if cursor is not None:
            params["cursor"] = cursor
        response = await raw_client.get("/users/stream", params=params)
        response.raise_for_status()
        page = response.json()["response"]
        users.extend(page["users"])
        if not page.get("hasMore"):
            break
        cursor = page["nextCursor"]
    return users

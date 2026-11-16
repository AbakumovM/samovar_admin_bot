import logging

import httpx

logger = logging.getLogger(__name__)


async def drop_user_connections(raw_client: httpx.AsyncClient, remnawave_id: int) -> bool:
    try:
        response = await raw_client.post(
            "/connections/drop",
            json={
                "dropBy": {"by": "userIds", "userIds": [remnawave_id]},
                "targetNodes": {"target": "allNodes"},
            },
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("drop-connections failed for %d: %s", remnawave_id, e)
        return False

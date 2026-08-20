from datetime import datetime

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.nodes.adapters.orm import MutedNodeModel


class RemnaWaveNodeGateway:
    def __init__(self, raw_client: httpx.AsyncClient, session: AsyncSession) -> None:
        self._raw_client = raw_client
        self._session = session

    async def restart_node(self, node_uuid: str) -> None:
        # Raw HTTP: the installed SDK's restart_node() takes no body param at
        # all, but the panel now requires `forceRestart` in the request body
        # — omitting it fails validation with HTTP 400 (SDK/panel version
        # mismatch, same class of issue as the other endpoints fixed
        # elsewhere in this codebase via raw_client).
        response = await self._raw_client.post(
            f"/nodes/{node_uuid}/actions/restart", json={"forceRestart": False}
        )
        response.raise_for_status()

    async def mute_node(
        self, node_uuid: str, muted_until: datetime, admin_telegram_id: int
    ) -> None:
        stmt = (
            insert(MutedNodeModel)
            .values(
                node_uuid=node_uuid,
                muted_until=muted_until,
                muted_by_telegram_id=admin_telegram_id,
            )
            .on_conflict_do_update(
                index_elements=["node_uuid"],
                set_={"muted_until": muted_until, "muted_by_telegram_id": admin_telegram_id},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def unmute_node(self, node_uuid: str) -> None:
        await self._session.execute(
            delete(MutedNodeModel).where(MutedNodeModel.node_uuid == node_uuid)
        )
        await self._session.flush()

from datetime import datetime

from remnawave import RemnawaveSDK
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.nodes.adapters.orm import MutedNodeModel


class RemnaWaveNodeGateway:
    def __init__(self, sdk: RemnawaveSDK, session: AsyncSession) -> None:
        self._sdk = sdk
        self._session = session

    async def restart_node(self, node_uuid: str) -> None:
        await self._sdk.nodes.restart_node(node_uuid)

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

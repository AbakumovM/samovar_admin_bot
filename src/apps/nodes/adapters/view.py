from datetime import datetime, timezone

from remnawave import RemnawaveSDK
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.nodes.adapters.orm import MutedNodeModel
from src.apps.nodes.domain.models import NodeInfo


def _to_node_info(dto: object) -> NodeInfo:  # type: ignore[return]
    # remnawave SDK returns NodeResponseDto — access fields by attribute
    return NodeInfo(
        uuid=str(dto.uuid),  # type: ignore[attr-defined]
        name=str(dto.name),  # type: ignore[attr-defined]
        address=str(dto.address),  # type: ignore[attr-defined]
        country_code=str(dto.country_code or "??"),  # type: ignore[attr-defined]
        provider=str(dto.provider.name if dto.provider else "unknown"),  # type: ignore[attr-defined]
        is_connected=bool(dto.is_connected),  # type: ignore[attr-defined]
        is_connecting=bool(dto.is_connecting),  # type: ignore[attr-defined]
        is_disabled=bool(dto.is_disabled),  # type: ignore[attr-defined]
        last_status_change=dto.last_status_change,  # type: ignore[attr-defined]
        last_status_message=str(dto.last_status_message or ""),  # type: ignore[attr-defined]
        xray_uptime=int(dto.xray_uptime or 0),  # type: ignore[attr-defined]
        users_online=int(dto.users_online or 0),  # type: ignore[attr-defined]
        traffic_used_bytes=int(dto.traffic_used_bytes or 0),  # type: ignore[attr-defined]
    )


class RemnaWaveNodeView:
    def __init__(self, sdk: RemnawaveSDK, session: AsyncSession) -> None:
        self._sdk = sdk
        self._session = session

    async def get_all_nodes(self) -> list[NodeInfo]:
        response = await self._sdk.nodes.get_all_nodes()
        return [_to_node_info(node) for node in response]

    async def get_node_by_name(self, name: str) -> NodeInfo | None:
        response = await self._sdk.nodes.get_all_nodes()
        for node in response:
            if node.name.lower() == name.lower():  # type: ignore[attr-defined]
                return _to_node_info(node)
        return None

    async def is_muted(self, node_uuid: str) -> bool:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(MutedNodeModel).where(
                MutedNodeModel.node_uuid == node_uuid,
                MutedNodeModel.muted_until > now,
            )
        )
        return result.scalar_one_or_none() is not None

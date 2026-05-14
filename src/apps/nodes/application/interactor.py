from datetime import UTC, datetime, timedelta

from src.apps.nodes.application.interfaces.gateway import NodeGateway
from src.apps.nodes.application.interfaces.view import NodeView
from src.apps.nodes.domain.exceptions import NodeNotFound
from src.apps.nodes.domain.models import NodeInfo


class NodeInteractor:
    def __init__(self, gateway: NodeGateway, view: NodeView) -> None:
        self._gateway = gateway
        self._view = view

    async def restart_node_by_name(self, name: str) -> NodeInfo:
        node = await self._view.get_node_by_name(name)
        if node is None:
            raise NodeNotFound(name)
        await self._gateway.restart_node(node.uuid)
        return node

    async def mute_node_by_name(
        self, name: str, duration: timedelta, admin_telegram_id: int
    ) -> NodeInfo:
        node = await self._view.get_node_by_name(name)
        if node is None:
            raise NodeNotFound(name)
        muted_until = datetime.now(UTC) + duration
        await self._gateway.mute_node(
            node_uuid=node.uuid,
            muted_until=muted_until,
            admin_telegram_id=admin_telegram_id,
        )
        return node

    async def unmute_node_by_name(self, name: str) -> NodeInfo:
        node = await self._view.get_node_by_name(name)
        if node is None:
            raise NodeNotFound(name)
        await self._gateway.unmute_node(node.uuid)
        return node

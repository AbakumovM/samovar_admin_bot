from datetime import datetime
from typing import Protocol


class NodeGateway(Protocol):
    async def restart_node(self, node_uuid: str) -> None: ...
    async def mute_node(
        self, node_uuid: str, muted_until: datetime, admin_telegram_id: int
    ) -> None: ...
    async def unmute_node(self, node_uuid: str) -> None: ...

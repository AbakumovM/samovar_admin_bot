from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.application.interfaces.view import IncidentView
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.nodes.application.interfaces.gateway import NodeGateway
from src.apps.nodes.application.interfaces.view import NodeView
from src.apps.nodes.domain.models import NodeInfo

NotifyFn = Callable[[str], Coroutine[Any, Any, None]]


class MonitoringLoop:
    def __init__(
        self,
        *,
        node_view: NodeView,
        node_gateway: NodeGateway,
        incident_interactor: IncidentInteractor,
        incident_view: IncidentView,
        notify: NotifyFn,
        escalation_window_minutes: int,
        escalation_max_attempts: int,
    ) -> None:
        self._node_view = node_view
        self._node_gateway = node_gateway
        self._incident_interactor = incident_interactor
        self._incident_view = incident_view
        self._notify = notify
        self._escalation_window_minutes = escalation_window_minutes
        self._escalation_max_attempts = escalation_max_attempts

    async def poll(self) -> None:
        now = datetime.now(timezone.utc)
        nodes = await self._node_view.get_all_nodes()
        for node in nodes:
            await self._process_node(node, now)

    async def _process_node(self, node: NodeInfo, now: datetime) -> None:
        if node.is_disabled:
            return

        # Always record snapshot
        await self._incident_interactor.record_snapshot(
            RecordSnapshot(
                node_uuid=node.uuid,
                captured_at=now,
                users_online=node.users_online,
                traffic_used_bytes=node.traffic_used_bytes,
                xray_uptime=node.xray_uptime,
                is_connected=node.is_connected,
            )
        )

        if not node.is_connected:
            await self._handle_offline_node(node, now)
        else:
            await self._handle_online_node(node, now)

    async def _handle_offline_node(self, node: NodeInfo, now: datetime) -> None:
        if await self._node_view.is_muted(node.uuid):
            return

        recent_count = await self._incident_view.count_recent_incidents(
            node.uuid, self._escalation_window_minutes
        )

        if recent_count >= self._escalation_max_attempts:
            # Escalate existing open incident
            open_incident = await self._incident_view.get_open_incident(node.uuid)
            if open_incident and not open_incident.escalated:
                await self._incident_interactor.escalate_incident(
                    EscalateIncident(incident_id=open_incident.id)
                )
                await self._notify(
                    f"🚨 [{node.name}] не поднимается после "
                    f"{self._escalation_max_attempts} попыток за час. "
                    f"Требуется ручное вмешательство!\n"
                    f"Причина: {node.last_status_message}"
                )
        else:
            # Open new incident if none exists
            open_incident = await self._incident_view.get_open_incident(node.uuid)
            if open_incident is None:
                open_incident = await self._incident_interactor.open_incident(
                    OpenIncident(
                        node_uuid=node.uuid,
                        node_name=node.name,
                        started_at=now,
                        last_status_message=node.last_status_message,
                    )
                )

            attempt_num = recent_count + 1
            await self._node_gateway.restart_node(node.uuid)
            await self._incident_interactor.record_restart_attempt(
                RecordRestartAttempt(incident_id=open_incident.id)
            )
            await self._notify(
                f"🔴 [{node.name}] упала. "
                f"Причина: {node.last_status_message}\n"
                f"Перезапуск (попытка {attempt_num}/{self._escalation_max_attempts})"
            )

    async def _handle_online_node(self, node: NodeInfo, now: datetime) -> None:
        open_incident = await self._incident_view.get_open_incident(node.uuid)
        if open_incident is None:
            return

        closed = await self._incident_interactor.close_incident(
            CloseIncident(incident_id=open_incident.id, resolved_at=now)
        )
        downtime_min = (closed.downtime_seconds or 0) // 60
        await self._notify(
            f"✅ [{node.name}] восстановлена. Даунтайм: {downtime_min} мин"
        )

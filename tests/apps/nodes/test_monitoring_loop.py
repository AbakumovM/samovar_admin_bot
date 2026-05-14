from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.apps.nodes.controllers.scheduler.loop import MonitoringLoop
from src.apps.nodes.domain.models import NodeInfo
from src.apps.incidents.domain.models import IncidentInfo


def make_node(
    *,
    uuid: str = "node-1",
    name: str = "DE-1",
    is_connected: bool = True,
) -> NodeInfo:
    return NodeInfo(
        uuid=uuid,
        name=name,
        address="1.2.3.4",
        country_code="DE",
        provider="AEZA",
        is_connected=is_connected,
        is_connecting=False,
        is_disabled=False,
        last_status_change=datetime.now(timezone.utc),
        last_status_message="connection timeout" if not is_connected else "ok",
        xray_uptime=3600,
        users_online=5,
        traffic_used_bytes=1024,
    )


def make_incident(*, node_uuid: str = "node-1", escalated: bool = False) -> IncidentInfo:
    return IncidentInfo(
        id=uuid4(),
        node_uuid=node_uuid,
        node_name="DE-1",
        started_at=datetime.now(timezone.utc),
        resolved_at=None,
        last_status_message="connection timeout",
        restart_attempts=0,
        escalated=escalated,
        downtime_seconds=None,
    )


@pytest.fixture
def node_view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def incident_interactor() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def incident_view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def notify() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def loop(
    node_view: AsyncMock,
    node_gateway: AsyncMock,
    incident_interactor: AsyncMock,
    incident_view: AsyncMock,
    notify: AsyncMock,
) -> MonitoringLoop:
    return MonitoringLoop(
        node_view=node_view,
        node_gateway=node_gateway,
        incident_interactor=incident_interactor,
        incident_view=incident_view,
        notify=notify,
        escalation_window_minutes=60,
        escalation_max_attempts=3,
    )


async def test_online_node_with_no_incident_does_nothing(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node_view.get_all_nodes.return_value = [make_node(is_connected=True)]
    node_view.is_muted.return_value = False
    incident_view.get_open_incident.return_value = None
    incident_view.count_recent_incidents.return_value = 0

    await loop.poll()

    node_gateway.restart_node.assert_not_awaited()
    notify.assert_not_awaited()


async def test_offline_node_triggers_restart_and_notification(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    incident_interactor: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=False)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = False
    incident_view.get_open_incident.return_value = None
    incident_view.count_recent_incidents.return_value = 1  # < 3
    incident = make_incident()
    incident_interactor.open_incident.return_value = incident
    incident_interactor.record_restart_attempt.return_value = incident

    await loop.poll()

    node_gateway.restart_node.assert_awaited_once_with("node-1")
    notify.assert_awaited()
    call_msg: str = notify.call_args[0][0]
    assert "DE-1" in call_msg
    assert "🔴" in call_msg


async def test_muted_offline_node_skips_restart(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=False)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = True

    await loop.poll()

    node_gateway.restart_node.assert_not_awaited()
    notify.assert_not_awaited()


async def test_three_incidents_triggers_escalation(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    incident_interactor: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=False)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = False
    incident = make_incident()
    incident_view.get_open_incident.return_value = incident
    incident_view.count_recent_incidents.return_value = 3  # >= 3 → escalate
    incident_interactor.escalate_incident.return_value = make_incident(escalated=True)

    await loop.poll()

    node_gateway.restart_node.assert_not_awaited()
    incident_interactor.escalate_incident.assert_awaited_once()
    notify.assert_awaited()
    call_msg: str = notify.call_args[0][0]
    assert "🚨" in call_msg


async def test_node_recovery_closes_incident(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    incident_interactor: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=True)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = False
    open_incident = make_incident()
    incident_view.get_open_incident.return_value = open_incident
    incident_interactor.close_incident.return_value = open_incident

    await loop.poll()

    incident_interactor.close_incident.assert_awaited_once()
    notify.assert_awaited()
    call_msg: str = notify.call_args[0][0]
    assert "✅" in call_msg

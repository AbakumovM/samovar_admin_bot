from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


def make_incident(
    *,
    node_uuid: str = "node-1",
    restart_attempts: int = 0,
    escalated: bool = False,
    resolved_at: datetime | None = None,
) -> IncidentInfo:
    return IncidentInfo(
        id=uuid4(),
        node_uuid=node_uuid,
        node_name="DE-1",
        started_at=datetime.now(timezone.utc),
        resolved_at=resolved_at,
        last_status_message="connection timeout",
        restart_attempts=restart_attempts,
        escalated=escalated,
        downtime_seconds=None,
    )


@pytest.fixture
def gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def interactor(gateway: AsyncMock, view: AsyncMock) -> IncidentInteractor:
    return IncidentInteractor(gateway=gateway, view=view)


async def test_open_incident_calls_gateway(
    interactor: IncidentInteractor, gateway: AsyncMock
) -> None:
    now = datetime.now(timezone.utc)
    cmd = OpenIncident(
        node_uuid="node-1",
        node_name="DE-1",
        started_at=now,
        last_status_message="timeout",
    )
    incident = make_incident()
    gateway.open_incident.return_value = incident

    result = await interactor.open_incident(cmd)

    gateway.open_incident.assert_awaited_once_with(cmd)
    assert result == incident


async def test_close_incident_computes_downtime(
    interactor: IncidentInteractor, gateway: AsyncMock, view: AsyncMock
) -> None:
    started = datetime.now(timezone.utc) - timedelta(minutes=6)
    incident = make_incident()
    open_incident = IncidentInfo(
        id=incident.id,
        node_uuid=incident.node_uuid,
        node_name=incident.node_name,
        started_at=started,
        resolved_at=None,
        last_status_message=incident.last_status_message,
        restart_attempts=incident.restart_attempts,
        escalated=incident.escalated,
        downtime_seconds=None,
    )
    view.get_open_incident.return_value = open_incident
    resolved_at = datetime.now(timezone.utc)
    closed = IncidentInfo(
        id=incident.id,
        node_uuid=incident.node_uuid,
        node_name=incident.node_name,
        started_at=started,
        resolved_at=resolved_at,
        last_status_message=incident.last_status_message,
        restart_attempts=incident.restart_attempts,
        escalated=incident.escalated,
        downtime_seconds=int((resolved_at - started).total_seconds()),
    )
    gateway.close_incident.return_value = closed
    cmd = CloseIncident(incident_id=incident.id, resolved_at=resolved_at)

    result = await interactor.close_incident(cmd)

    gateway.close_incident.assert_awaited_once_with(cmd)
    assert result.downtime_seconds is not None
    assert result.downtime_seconds > 0


async def test_record_restart_attempt(
    interactor: IncidentInteractor, gateway: AsyncMock
) -> None:
    incident = make_incident(restart_attempts=1)
    gateway.record_restart_attempt.return_value = incident
    cmd = RecordRestartAttempt(incident_id=incident.id)

    result = await interactor.record_restart_attempt(cmd)

    gateway.record_restart_attempt.assert_awaited_once_with(cmd)
    assert result == incident


async def test_escalate_incident(
    interactor: IncidentInteractor, gateway: AsyncMock
) -> None:
    incident = make_incident(escalated=True)
    gateway.escalate_incident.return_value = incident
    cmd = EscalateIncident(incident_id=incident.id)

    result = await interactor.escalate_incident(cmd)

    gateway.escalate_incident.assert_awaited_once_with(cmd)
    assert result.escalated is True


def test_incident_info_is_frozen() -> None:
    now = datetime.now(UTC)
    incident = IncidentInfo(
        id=uuid4(),
        node_uuid="node-1",
        node_name="DE-1",
        started_at=now,
        resolved_at=None,
        last_status_message="connection timeout",
        restart_attempts=0,
        escalated=False,
        downtime_seconds=None,
    )
    try:
        incident.escalated = True  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass


def test_snapshot_info_is_frozen() -> None:
    now = datetime.now(UTC)
    snap = NodeStatsSnapshotInfo(
        id=uuid4(),
        node_uuid="node-1",
        captured_at=now,
        users_online=5,
        traffic_used_bytes=1024,
        xray_uptime=3600,
        is_connected=True,
    )
    try:
        snap.users_online = 10  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass

from datetime import UTC, datetime
from uuid import uuid4

from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


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

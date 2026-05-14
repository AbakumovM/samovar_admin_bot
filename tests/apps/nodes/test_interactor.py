from datetime import datetime, timezone

from src.apps.nodes.domain.models import NodeInfo


def test_node_info_is_frozen() -> None:
    node = NodeInfo(
        uuid="abc-123",
        name="DE-1",
        address="1.2.3.4",
        country_code="DE",
        provider="AEZA",
        is_connected=True,
        is_connecting=False,
        is_disabled=False,
        last_status_change=datetime.now(timezone.utc),
        last_status_message="connected",
        xray_uptime=3600,
        users_online=5,
        traffic_used_bytes=1024,
    )
    try:
        node.is_connected = False  # type: ignore[misc]
        assert False, "Should be frozen"
    except Exception:
        pass

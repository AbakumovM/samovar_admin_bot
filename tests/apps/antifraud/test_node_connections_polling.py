from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.apps.antifraud.controllers.scheduler.tasks import _fetch_node_connections
from src.apps.antifraud.domain.models import IpSighting, NodeUserConnections


def _response(json_body: dict) -> MagicMock:  # type: ignore[type-arg]
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"response": json_body})
    return response


def _make_raw_client(*, post_response: MagicMock, get_responses: list[MagicMock]) -> MagicMock:  # type: ignore[type-arg]
    raw_client = MagicMock()
    raw_client.post = AsyncMock(return_value=post_response)
    raw_client.get = AsyncMock(side_effect=get_responses)
    return raw_client


_TRIGGER_OK = _response({"jobId": "job-1"})


async def test_fetch_node_connections_success() -> None:
    completed = _response({
        "isCompleted": True,
        "isFailed": False,
        "result": {
            "success": True,
            "nodeUuid": "node-1",
            "users": [
                {"userId": 42, "ips": [{"ip": "1.2.3.4", "lastSeen": "2026-08-18T00:00:00Z"}]}
            ],
        },
    })
    raw_client = _make_raw_client(post_response=_TRIGGER_OK, get_responses=[completed])

    result = await _fetch_node_connections(
        raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=1.0
    )

    assert result.ok is True
    expected_seen = datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)
    assert result.users == (
        NodeUserConnections(
            user_id=42, ips=(IpSighting(ip="1.2.3.4", last_seen=expected_seen),)
        ),
    )


async def test_fetch_node_connections_polls_until_completed() -> None:
    pending = _response({"isCompleted": False, "isFailed": False, "result": None})
    completed = _response({
        "isCompleted": True,
        "isFailed": False,
        "result": {"success": True, "nodeUuid": "node-1", "users": []},
    })
    raw_client = _make_raw_client(post_response=_TRIGGER_OK, get_responses=[pending, completed])

    with patch("src.apps.antifraud.controllers.scheduler.tasks.asyncio.sleep", AsyncMock()):
        result = await _fetch_node_connections(
            raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=1.0
        )

    assert result.ok is True
    assert raw_client.get.await_count == 2


async def test_fetch_node_connections_timeout_returns_ok_false() -> None:
    pending = _response({"isCompleted": False, "isFailed": False, "result": None})
    raw_client = _make_raw_client(post_response=_TRIGGER_OK, get_responses=[pending] * 100)

    result = await _fetch_node_connections(
        raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=0.03
    )

    assert result.ok is False
    assert result.failure_reason is not None and "timed out" in result.failure_reason


async def test_fetch_node_connections_is_failed_returns_ok_false() -> None:
    failed = _response({"isCompleted": True, "isFailed": True, "result": None})
    raw_client = _make_raw_client(post_response=_TRIGGER_OK, get_responses=[failed])

    result = await _fetch_node_connections(
        raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=1.0
    )

    assert result.ok is False
    assert result.failure_reason == "job isFailed"


async def test_fetch_node_connections_success_false_returns_ok_false() -> None:
    not_success = _response({
        "isCompleted": True,
        "isFailed": False,
        "result": {"success": False, "nodeUuid": "node-1", "users": []},
    })
    raw_client = _make_raw_client(post_response=_TRIGGER_OK, get_responses=[not_success])

    result = await _fetch_node_connections(
        raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=1.0
    )

    assert result.ok is False


async def test_fetch_node_connections_trigger_http_error_returns_ok_false() -> None:
    raw_client = MagicMock()
    raw_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock())
    )
    raw_client.get = AsyncMock()

    result = await _fetch_node_connections(
        raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=1.0
    )

    assert result.ok is False
    assert result.failure_reason is not None and "trigger failed" in result.failure_reason
    raw_client.get.assert_not_awaited()


async def test_fetch_node_connections_ip_dedup_within_node() -> None:
    completed = _response({
        "isCompleted": True,
        "isFailed": False,
        "result": {
            "success": True,
            "nodeUuid": "node-1",
            "users": [
                {
                    "userId": 42,
                    "ips": [
                        {"ip": "1.2.3.4", "lastSeen": "2026-08-18T00:00:00Z"},
                        {"ip": "1.2.3.4", "lastSeen": "2026-08-18T00:00:01Z"},
                    ],
                }
            ],
        },
    })
    raw_client = _make_raw_client(post_response=_TRIGGER_OK, get_responses=[completed])

    result = await _fetch_node_connections(
        raw_client, "node-1", "DE-1", poll_interval_seconds=0.01, timeout_seconds=1.0
    )

    ips = result.users[0].ips
    assert len(ips) == 1
    assert ips[0].ip == "1.2.3.4"
    assert ips[0].last_seen == datetime(2026, 8, 18, 0, 0, 1, tzinfo=UTC)  # keeps latest

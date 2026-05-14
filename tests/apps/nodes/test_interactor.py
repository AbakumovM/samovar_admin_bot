from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.apps.nodes.application.interactor import NodeInteractor
from src.apps.nodes.domain.exceptions import NodeNotFound
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
        last_status_change=datetime.now(UTC),
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


def make_node(*, name: str = "DE-1", uuid: str = "node-1", is_connected: bool = True) -> NodeInfo:
    return NodeInfo(
        uuid=uuid,
        name=name,
        address="1.2.3.4",
        country_code="DE",
        provider="AEZA",
        is_connected=is_connected,
        is_connecting=False,
        is_disabled=False,
        last_status_change=datetime.now(UTC),
        last_status_message="ok",
        xray_uptime=3600,
        users_online=5,
        traffic_used_bytes=1024,
    )


@pytest.fixture
def node_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_interactor(node_gateway: AsyncMock, node_view: AsyncMock) -> NodeInteractor:
    return NodeInteractor(gateway=node_gateway, view=node_view)


async def test_restart_node_calls_gateway(
    node_interactor: NodeInteractor,
    node_gateway: AsyncMock,
    node_view: AsyncMock,
) -> None:
    node = make_node()
    node_view.get_node_by_name.return_value = node

    await node_interactor.restart_node_by_name("DE-1")

    node_gateway.restart_node.assert_awaited_once_with("node-1")


async def test_restart_node_raises_if_not_found(
    node_interactor: NodeInteractor,
    node_view: AsyncMock,
) -> None:
    node_view.get_node_by_name.return_value = None

    with pytest.raises(NodeNotFound):
        await node_interactor.restart_node_by_name("XX-99")


async def test_mute_node_by_name(
    node_interactor: NodeInteractor,
    node_gateway: AsyncMock,
    node_view: AsyncMock,
) -> None:
    node = make_node()
    node_view.get_node_by_name.return_value = node
    duration = timedelta(hours=1)

    await node_interactor.mute_node_by_name("DE-1", duration, admin_telegram_id=123)

    node_gateway.mute_node.assert_awaited_once()
    call_args = node_gateway.mute_node.call_args
    assert call_args.kwargs["node_uuid"] == "node-1"
    assert call_args.kwargs["admin_telegram_id"] == 123

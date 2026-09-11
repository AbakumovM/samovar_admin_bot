from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from src.apps.billing.adapters.view import RemnawaveBillingView

_NODE_UUID = UUID("11111111-0000-0000-0000-000000000001")
_BILLING_UUID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_PROVIDER_UUID = UUID("22222222-0000-0000-0000-000000000001")
_DT = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


def _make_sdk_billing_node(
    node_name: str = "RU-MSK-01",
    provider_name: str = "Hetzner",
    login_url: str | None = "https://accounts.hetzner.com",
    next_billing_at: datetime = _DT,
) -> MagicMock:
    bn = MagicMock()
    bn.uuid = _BILLING_UUID
    bn.node_uuid = _NODE_UUID
    bn.provider_uuid = _PROVIDER_UUID
    bn.next_billing_at = next_billing_at
    bn.provider = MagicMock()
    bn.provider.name = provider_name
    bn.provider.login_url = login_url
    bn.node = MagicMock()
    bn.node.uuid = _NODE_UUID
    bn.node.name = node_name
    return bn


def _make_stats(upcoming: int = 1) -> MagicMock:
    s = MagicMock()
    s.upcoming_nodes_count = upcoming
    return s


async def test_get_billing_nodes_maps_fields() -> None:
    sdk = MagicMock()
    response = MagicMock()
    response.billing_nodes = [_make_sdk_billing_node()]
    response.stats = _make_stats()
    sdk.infra_billing.get_billing_nodes = AsyncMock(return_value=response)

    view = RemnawaveBillingView(sdk=sdk)
    nodes = await view.get_billing_nodes()

    assert len(nodes) == 1
    assert nodes[0].node_name == "RU-MSK-01"
    assert nodes[0].provider_name == "Hetzner"
    assert nodes[0].provider_login_url == "https://accounts.hetzner.com"
    assert nodes[0].uuid == str(_BILLING_UUID)
    assert nodes[0].next_billing_at == _DT


async def test_get_billing_stats_maps_fields() -> None:
    sdk = MagicMock()
    response = MagicMock()
    response.billing_nodes = []
    response.stats = _make_stats(upcoming=2)
    sdk.infra_billing.get_billing_nodes = AsyncMock(return_value=response)

    view = RemnawaveBillingView(sdk=sdk)
    stats = await view.get_billing_stats()

    assert stats.upcoming_nodes_count == 2

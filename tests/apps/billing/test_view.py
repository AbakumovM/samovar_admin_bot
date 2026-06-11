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


def _make_stats(upcoming: int = 1, monthly: float = 1500.0, total: float = 9000.0) -> MagicMock:
    s = MagicMock()
    s.upcoming_nodes_count = upcoming
    s.current_month_payments = monthly
    s.total_spent = total
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
    response.stats = _make_stats(upcoming=2, monthly=3000.0, total=18000.0)
    sdk.infra_billing.get_billing_nodes = AsyncMock(return_value=response)

    view = RemnawaveBillingView(sdk=sdk)
    stats = await view.get_billing_stats()

    assert stats.upcoming_nodes_count == 2
    assert stats.current_month_payments == 3000.0
    assert stats.total_spent == 18000.0


async def test_get_payment_history_resolves_names() -> None:
    sdk = MagicMock()

    nodes_resp = MagicMock()
    nodes_resp.billing_nodes = [_make_sdk_billing_node()]
    nodes_resp.stats = _make_stats()

    record = MagicMock()
    record.uuid = UUID("bbbbbbbb-0000-0000-0000-000000000001")
    record.node_uuid = _NODE_UUID
    record.provider_uuid = _PROVIDER_UUID
    record.amount = 1500.0
    record.payment_date = _DT

    history_resp = MagicMock()
    history_resp.records = [record]

    sdk.infra_billing.get_billing_nodes = AsyncMock(return_value=nodes_resp)
    sdk.infra_billing.get_infra_billing_history_records = AsyncMock(return_value=history_resp)

    view = RemnawaveBillingView(sdk=sdk)
    records = await view.get_payment_history(limit=10)

    assert len(records) == 1
    assert records[0].node_name == "RU-MSK-01"
    assert records[0].provider_name == "Hetzner"
    assert records[0].amount == 1500.0


async def test_get_payment_history_unknown_node() -> None:
    sdk = MagicMock()
    nodes_resp = MagicMock()
    nodes_resp.billing_nodes = []
    nodes_resp.stats = _make_stats()

    record = MagicMock()
    record.uuid = UUID("cccccccc-0000-0000-0000-000000000001")
    record.node_uuid = _NODE_UUID
    record.provider_uuid = _PROVIDER_UUID
    record.amount = 500.0
    record.payment_date = _DT

    history_resp = MagicMock()
    history_resp.records = [record]

    sdk.infra_billing.get_billing_nodes = AsyncMock(return_value=nodes_resp)
    sdk.infra_billing.get_infra_billing_history_records = AsyncMock(return_value=history_resp)

    view = RemnawaveBillingView(sdk=sdk)
    records = await view.get_payment_history()

    assert records[0].node_name == "Неизвестная нода"
    assert records[0].provider_name == "Неизвестный провайдер"

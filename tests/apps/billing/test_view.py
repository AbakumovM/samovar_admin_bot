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


def _make_raw_client(json_body: dict) -> MagicMock:  # type: ignore[type-arg]
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=json_body)
    raw_client = MagicMock()
    raw_client.get = AsyncMock(return_value=response)
    return raw_client


async def test_get_billing_nodes_maps_fields() -> None:
    sdk = MagicMock()
    response = MagicMock()
    response.billing_nodes = [_make_sdk_billing_node()]
    response.stats = _make_stats()
    sdk.infra_billing.get_billing_nodes = AsyncMock(return_value=response)

    view = RemnawaveBillingView(sdk=sdk, raw_client=MagicMock())
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

    view = RemnawaveBillingView(sdk=sdk, raw_client=MagicMock())
    stats = await view.get_billing_stats()

    assert stats.upcoming_nodes_count == 2
    assert stats.current_month_payments == 3000.0
    assert stats.total_spent == 18000.0


async def test_get_payment_history_resolves_names() -> None:
    # Panel v3.2.3: history records carry a `provider` object but no node
    # reference — the record isn't tied to a specific node anymore.
    raw_client = _make_raw_client({
        "response": {
            "records": [
                {
                    "uuid": "bbbbbbbb-0000-0000-0000-000000000001",
                    "providerUuid": str(_PROVIDER_UUID),
                    "amount": 1500.0,
                    "billedAt": "2026-07-14T12:00:00.000Z",
                    "provider": {"uuid": str(_PROVIDER_UUID), "name": "Hetzner"},
                }
            ],
            "total": 1,
        }
    })

    view = RemnawaveBillingView(sdk=MagicMock(), raw_client=raw_client)
    records = await view.get_payment_history(limit=10)

    assert len(records) == 1
    assert records[0].provider_name == "Hetzner"
    assert records[0].amount == 1500.0
    assert records[0].payment_date == _DT


async def test_get_payment_history_sorts_by_billed_at_descending() -> None:
    raw_client = _make_raw_client({
        "response": {
            "records": [
                {
                    "uuid": "cccccccc-0000-0000-0000-000000000001",
                    "providerUuid": str(_PROVIDER_UUID),
                    "amount": 500.0,
                    "billedAt": "2026-06-01T12:00:00.000Z",
                    "provider": {"uuid": str(_PROVIDER_UUID), "name": "Hetzner"},
                },
                {
                    "uuid": "dddddddd-0000-0000-0000-000000000001",
                    "providerUuid": str(_PROVIDER_UUID),
                    "amount": 700.0,
                    "billedAt": "2026-07-01T12:00:00.000Z",
                    "provider": {"uuid": str(_PROVIDER_UUID), "name": "Hetzner"},
                },
            ],
            "total": 2,
        }
    })

    view = RemnawaveBillingView(sdk=MagicMock(), raw_client=raw_client)
    records = await view.get_payment_history()

    assert [r.amount for r in records] == [700.0, 500.0]

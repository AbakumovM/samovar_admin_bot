from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo, PaymentRecordInfo

_UUID_STR = "00000000-0000-0000-0000-000000000001"
_DT = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


def test_billing_node_info_is_frozen() -> None:
    node = BillingNodeInfo(
        uuid=_UUID_STR, node_uuid=_UUID_STR, node_name="RU-MSK-01",
        provider_uuid=_UUID_STR, provider_name="Hetzner",
        provider_login_url="https://accounts.hetzner.com",
        next_billing_at=_DT, days_until=3,
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        node.days_until = 5  # type: ignore[misc]


def test_payment_record_info_is_frozen() -> None:
    record = PaymentRecordInfo(
        uuid=_UUID_STR, node_name="RU-MSK-01", provider_name="Hetzner",
        amount=1500.0, payment_date=_DT,
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        record.amount = 999.0  # type: ignore[misc]


def test_billing_stats_is_frozen() -> None:
    stats = BillingStatsInfo(
        upcoming_nodes_count=3, current_month_payments=4500.0, total_spent=27000.0
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        stats.upcoming_nodes_count = 99  # type: ignore[misc]


def test_billing_stats_fields() -> None:
    stats = BillingStatsInfo(
        upcoming_nodes_count=3, current_month_payments=4500.0, total_spent=27000.0
    )
    assert stats.upcoming_nodes_count == 3
    assert stats.total_spent == 27000.0

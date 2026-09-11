from datetime import UTC, datetime

from src.apps.billing.controllers.telegram.handlers import _format_billing_overview
from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo

_UUID_STR = "00000000-0000-0000-0000-000000000001"
_DT = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


def _node(days_until: int) -> BillingNodeInfo:
    return BillingNodeInfo(
        uuid=_UUID_STR,
        node_uuid=_UUID_STR,
        node_name="RU-MSK-01",
        provider_uuid=_UUID_STR,
        provider_name="Hetzner",
        provider_login_url=None,
        next_billing_at=_DT,
        days_until=days_until,
    )


def _stats() -> BillingStatsInfo:
    return BillingStatsInfo(upcoming_nodes_count=1)


def test_format_overview_warning_icon_when_within_threshold() -> None:
    text = _format_billing_overview([_node(2)], _stats(), alert_days=3)
    assert "⚠️" in text
    assert "RU-MSK-01" in text


def test_format_overview_no_warning_beyond_threshold() -> None:
    text = _format_billing_overview([_node(10)], _stats(), alert_days=3)
    assert "⚠️" not in text


def test_format_overview_shows_upcoming_count() -> None:
    text = _format_billing_overview([_node(5)], _stats(), alert_days=3)
    assert "Предстоящих платежей: 1" in text


def test_format_overview_empty_nodes() -> None:
    stats = BillingStatsInfo(upcoming_nodes_count=0)
    text = _format_billing_overview([], stats, alert_days=3)
    assert "нод" in text.lower()


def test_format_overview_overdue_node_shows_overdue_text() -> None:
    text = _format_billing_overview([_node(-4)], _stats(), alert_days=3)
    assert "просрочен на 4 дн." in text
    assert "⚠️" in text

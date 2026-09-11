from datetime import UTC, datetime

from src.apps.billing.controllers.scheduler.tasks import _format_billing_alert
from src.apps.billing.domain.models import BillingNodeInfo

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


def test_format_alert_upcoming_payment() -> None:
    text = _format_billing_alert(_node(2))
    assert "Предстоящий платёж" in text
    assert "через 2 дн." in text
    assert "🔴" not in text


def test_format_alert_due_today() -> None:
    text = _format_billing_alert(_node(0))
    assert "сегодня!" in text


def test_format_alert_overdue_payment() -> None:
    text = _format_billing_alert(_node(-5))
    assert "🔴" in text
    assert "просрочен на 5 дн." in text

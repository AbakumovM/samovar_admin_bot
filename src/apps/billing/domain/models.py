from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BillingNodeInfo:
    uuid: str
    node_uuid: str
    node_name: str
    provider_uuid: str
    provider_name: str
    provider_login_url: str | None
    next_billing_at: datetime
    days_until: int


@dataclass(frozen=True)
class PaymentRecordInfo:
    uuid: str
    node_name: str
    provider_name: str
    amount: float
    payment_date: datetime


@dataclass(frozen=True)
class BillingStatsInfo:
    upcoming_nodes_count: int
    current_month_payments: float
    total_spent: float

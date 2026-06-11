from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class BillingNodeInfo:
    uuid: UUID
    node_uuid: UUID
    node_name: str
    provider_uuid: UUID
    provider_name: str
    provider_login_url: str | None
    next_billing_at: datetime
    days_until: int


@dataclass(frozen=True)
class PaymentRecordInfo:
    uuid: UUID
    node_name: str
    provider_name: str
    amount: float
    payment_date: datetime


@dataclass(frozen=True)
class BillingStatsInfo:
    upcoming_nodes_count: int
    current_month_payments: float
    total_spent: float

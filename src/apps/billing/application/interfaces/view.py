from typing import Protocol

from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo


class BillingView(Protocol):
    async def get_billing_nodes(self) -> list[BillingNodeInfo]: ...
    async def get_billing_stats(self) -> BillingStatsInfo: ...

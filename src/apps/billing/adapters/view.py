from datetime import UTC, datetime

import httpx
from remnawave import RemnawaveSDK

from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo, PaymentRecordInfo


class RemnawaveBillingView:
    def __init__(self, sdk: RemnawaveSDK, raw_client: httpx.AsyncClient) -> None:
        self._sdk = sdk
        self._raw_client = raw_client

    async def get_billing_nodes(self) -> list[BillingNodeInfo]:
        response = await self._sdk.infra_billing.get_billing_nodes()
        today = datetime.now(UTC).date()
        nodes = [
            BillingNodeInfo(
                uuid=str(node.uuid),
                node_uuid=str(node.node_uuid),
                node_name=node.node.name,
                provider_uuid=str(node.provider_uuid),
                provider_name=node.provider.name,
                provider_login_url=node.provider.login_url,
                next_billing_at=node.next_billing_at,
                days_until=(node.next_billing_at.astimezone(UTC).date() - today).days,
            )
            for node in response.billing_nodes
        ]
        return sorted(nodes, key=lambda n: n.next_billing_at)

    async def get_billing_stats(self) -> BillingStatsInfo:
        response = await self._sdk.infra_billing.get_billing_nodes()
        stats = response.stats
        return BillingStatsInfo(
            upcoming_nodes_count=int(stats.upcoming_nodes_count),
            current_month_payments=float(stats.current_month_payments),
            total_spent=float(stats.total_spent),
        )

    async def get_payment_history(self, limit: int = 10) -> list[PaymentRecordInfo]:
        # Raw HTTP: panel v3.2.3 dropped `nodeUuid` from history records —
        # payments are now tracked per-provider, not per-node — and the SDK's
        # response model still requires the old (now-missing) fields.
        response = await self._raw_client.get(
            "/infra-billing/history", params={"start": 0, "size": limit}
        )
        response.raise_for_status()
        records = response.json()["response"]["records"]
        records.sort(key=lambda r: r["billedAt"], reverse=True)
        return [
            PaymentRecordInfo(
                uuid=str(record["uuid"]),
                provider_name=str(record["provider"]["name"]),
                amount=float(record["amount"]),
                payment_date=datetime.fromisoformat(record["billedAt"].replace("Z", "+00:00")),
            )
            for record in records[:limit]
        ]

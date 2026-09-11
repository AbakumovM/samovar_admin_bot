from datetime import UTC, datetime

from remnawave import RemnawaveSDK

from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo


class RemnawaveBillingView:
    def __init__(self, sdk: RemnawaveSDK) -> None:
        self._sdk = sdk

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
        return BillingStatsInfo(upcoming_nodes_count=int(response.stats.upcoming_nodes_count))

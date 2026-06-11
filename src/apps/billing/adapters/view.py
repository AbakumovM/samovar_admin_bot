from datetime import datetime, timezone
from uuid import UUID

from remnawave import RemnawaveSDK

from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo, PaymentRecordInfo


class RemnawaveBillingView:
    def __init__(self, sdk: RemnawaveSDK) -> None:
        self._sdk = sdk

    async def get_billing_nodes(self) -> list[BillingNodeInfo]:
        response = await self._sdk.infra_billing.get_billing_nodes()
        today = datetime.now(timezone.utc).date()
        nodes = [
            BillingNodeInfo(
                uuid=str(node.uuid),
                node_uuid=str(node.node_uuid),
                node_name=node.node.name,
                provider_uuid=str(node.provider_uuid),
                provider_name=node.provider.name,
                provider_login_url=node.provider.login_url,
                next_billing_at=node.next_billing_at,
                days_until=(node.next_billing_at.astimezone(timezone.utc).date() - today).days,
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
        nodes_resp = await self._sdk.infra_billing.get_billing_nodes()
        history_resp = await self._sdk.infra_billing.get_infra_billing_history_records()
        node_name_map: dict[UUID, str] = {
            n.node.uuid: n.node.name for n in nodes_resp.billing_nodes
        }
        provider_name_map: dict[UUID, str] = {
            n.provider_uuid: n.provider.name for n in nodes_resp.billing_nodes
        }
        records = sorted(history_resp.records, key=lambda r: r.payment_date, reverse=True)
        return [
            PaymentRecordInfo(
                uuid=str(record.uuid),
                node_name=node_name_map.get(record.node_uuid, "Неизвестная нода"),
                provider_name=provider_name_map.get(record.provider_uuid, "Неизвестный провайдер"),
                amount=float(record.amount),
                payment_date=record.payment_date,
            )
            for record in records[:limit]
        ]

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.incidents.adapters.view import PostgresIncidentView
from src.apps.incidents.domain.models import IncidentInfo
from src.apps.users.domain.models import UserTrafficDailyInfo
from src.config import Config

logger = logging.getLogger(__name__)

NotifyFn = Callable[[str], Coroutine[Any, Any, None]]


def _build_daily_report(
    incidents: list[IncidentInfo],
    top_traffic: list[UserTrafficDailyInfo] | None = None,
) -> str:
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    if not incidents:
        return f"📊 Ежедневный отчёт — {date_str}\n\nЗа прошедшие сутки инцидентов не было. ✅"

    by_node: dict[str, list[IncidentInfo]] = {}
    for inc in incidents:
        by_node.setdefault(inc.node_name, []).append(inc)

    lines = [f"📊 Ежедневный отчёт — {date_str}\n"]
    lines.append(
        f"Инцидентов: <b>{len(incidents)}</b> | "
        f"Нод с проблемами: <b>{len(by_node)}</b>\n"
    )

    for node_name, node_incidents in sorted(by_node.items()):
        total_downtime = sum(i.downtime_seconds or 0 for i in node_incidents)
        escalated = any(i.escalated for i in node_incidents)
        active = any(i.resolved_at is None for i in node_incidents)
        reasons = {i.last_status_message for i in node_incidents}
        total_restarts = sum(i.restart_attempts for i in node_incidents)

        icon = "🚨" if escalated else "🔴"
        lines.append(f"{icon} <b>{node_name}</b> — {len(node_incidents)} инц. | рестартов: {total_restarts}")
        lines.append(f"  Даунтайм: {total_downtime // 60} мин")
        if active:
            lines.append("  ⚠️ Есть активный инцидент")
        if escalated:
            lines.append("  🚨 Была эскалация")
        for reason in reasons:
            lines.append(f"  Причина: {reason}")

    if top_traffic:
        lines.append("\n📈 Топ-5 потребителей дня:")
        for i, rec in enumerate(top_traffic[:5], 1):
            gb = rec.bytes_consumed / 1024**3
            anomaly = " ⚠️" if rec.anomaly_alerted else ""
            lines.append(f"  {i}. {rec.username} — {gb:.1f} GB{anomaly}")

    return "\n".join(lines)


async def daily_report_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    notify: NotifyFn,
) -> None:
    while True:
        now = datetime.now(timezone.utc)
        next_report = now.replace(
            hour=config.daily_report_hour_utc, minute=0, second=0, microsecond=0
        )
        if next_report <= now:
            next_report += timedelta(days=1)
        sleep_seconds = (next_report - now).total_seconds()
        logger.info(
            "Daily report scheduled in %.0fs (at %s UTC)",
            sleep_seconds,
            next_report.strftime("%H:%M"),
        )
        await asyncio.sleep(sleep_seconds)

        try:
            from src.apps.users.adapters.view import PostgresUserTrafficView

            async with session_factory() as session:
                async with session.begin():
                    view = PostgresIncidentView(session=session)
                    incidents = await view.get_incidents_by_period(days=1)
                    traffic_view = PostgresUserTrafficView(session=session)
                    top_traffic = await traffic_view.get_top_traffic_today(limit=5)
            report = _build_daily_report(incidents, top_traffic=top_traffic)
            await notify(report)
        except Exception as e:
            logger.error("Daily report error: %s", e)

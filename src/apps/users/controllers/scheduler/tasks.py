import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.users.adapters.gateway import PostgresUserTrafficGateway
from src.apps.users.adapters.view import PostgresUserTrafficView
from src.apps.users.controllers.scheduler.alerts import (
    ThresholdAlert,
    format_threshold_alert,
    is_spike,
    make_block_keyboard,
    pick_threshold,
)
from src.apps.users.domain.commands import (
    AddHourlyTraffic,
    MarkAnomalyAlerted,
    MarkThresholdsAlerted,
    PurgeTrafficHistory,
    UpdateLastSnapshot,
    UpsertDailyTraffic,
)
from src.config import Config
from src.infrastructure.remnawave.pagination import fetch_all_users_stream

logger = logging.getLogger(__name__)

_WINDOW = timedelta(hours=24)
_HISTORY_RETENTION = timedelta(hours=25)
_ALERT_LIMIT = 10  # Prevent Telegram flood if thresholds misconfigured; critical alerts bypass it


def _compute_delta(current: int, previous: int) -> int | None:
    """Return bytes consumed since last snapshot. None means counter was reset."""
    delta = current - previous
    if delta < 0:
        return None
    return delta


def _order_and_limit(
    alerts: list[ThresholdAlert], critical_threshold_gb: int, limit: int
) -> list[ThresholdAlert]:
    """All critical alerts first, then at most `limit` regular ones, heaviest first."""
    critical = [a for a in alerts if a.threshold_gb >= critical_threshold_gb]
    regular = [a for a in alerts if a.threshold_gb < critical_threshold_gb]
    critical.sort(key=lambda a: a.total_bytes, reverse=True)
    regular.sort(key=lambda a: a.total_bytes, reverse=True)
    return critical + regular[:limit]


async def _fetch_all_users(raw_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    all_users = await fetch_all_users_stream(raw_client)
    return [
        u
        for u in all_users
        if str(u.get("status", "")).lower() == "active" and u.get("telegramId") is not None
    ]


async def _send_to_admins(bot: Bot, admin_ids: list[int], alert: ThresholdAlert, text: str) -> None:
    keyboard = make_block_keyboard(alert.user_uuid, alert.telegram_id, alert.total_bytes)
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=keyboard)
        except Exception as e:
            logger.error("Failed to send traffic alert to admin %s: %s", admin_id, e)


async def _run_traffic_check(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    bot: Bot,
) -> None:
    now = datetime.now(UTC)
    today = now.date()  # UTC date — requires server/container to run in UTC (Docker default)

    users = await _fetch_all_users(raw_client)
    logger.info("Traffic check: %d active users to process", len(users))

    # uuid -> (username, telegram_id) for users who consumed traffic this tick
    active: dict[str, tuple[str, int]] = {}

    # Transaction 1: process user snapshots, daily and hourly traffic
    async with session_factory() as session:
        async with session.begin():
            gateway = PostgresUserTrafficGateway(session=session)
            view = PostgresUserTrafficView(session=session)

            for user in users:
                # Panel v3.2.3 dropped per-user `uuid` — `id` (numeric) is the
                # stable identifier now. Field kept as `user_uuid` to match
                # the existing DB column/domain naming.
                user_uuid = str(user["id"])
                username = str(user["username"])
                current_bytes = int((user.get("userTraffic") or {}).get("usedTrafficBytes", 0) or 0)

                snapshot = await view.get_last_snapshot(user_uuid)

                await gateway.update_last_snapshot(
                    UpdateLastSnapshot(
                        user_uuid=user_uuid,
                        username=username,
                        used_bytes=current_bytes,
                        recorded_at=now,
                    )
                )

                if snapshot is None:
                    continue  # First run — establish baseline, compute delta next tick

                delta = _compute_delta(current=current_bytes, previous=snapshot.used_bytes)
                if delta is None:
                    continue  # Counter was reset (e.g. traffic reset by admin)
                if delta == 0:
                    continue  # No new traffic since last check

                await gateway.upsert_daily_traffic(
                    UpsertDailyTraffic(
                        user_uuid=user_uuid,
                        username=username,
                        date=today,
                        delta_bytes=delta,
                    )
                )
                await gateway.add_hourly_traffic(
                    AddHourlyTraffic(user_uuid=user_uuid, recorded_at=now, delta_bytes=delta)
                )
                active[user_uuid] = (username, int(user["telegramId"]))

            await gateway.purge_traffic_history(
                PurgeTrafficHistory(before=now - _HISTORY_RETENTION)
            )

    # Transaction 2: threshold detection over the rolling 24h window
    async with session_factory() as session:
        async with session.begin():
            gateway = PostgresUserTrafficGateway(session=session)
            view = PostgresUserTrafficView(session=session)

            since = now - _WINDOW
            totals = await view.get_traffic_since(list(active), since)
            alerted = await view.get_alerted_thresholds_since(list(active), since)

            candidates: list[ThresholdAlert] = []
            for user_uuid, total in totals.items():
                threshold = pick_threshold(
                    total, config.traffic_alert_thresholds_gb, alerted.get(user_uuid, set())
                )
                if threshold is None:
                    continue
                username, telegram_id = active[user_uuid]
                candidates.append(
                    ThresholdAlert(
                        user_uuid=user_uuid,
                        username=username,
                        telegram_id=telegram_id,
                        total_bytes=total,
                        threshold_gb=threshold,
                    )
                )

            selected = _order_and_limit(
                candidates, config.traffic_critical_threshold_gb, _ALERT_LIMIT
            )
            if len(selected) < len(candidates):
                logger.warning(
                    "Traffic alert limit reached (%d), suppressing %d alerts until next check",
                    _ALERT_LIMIT,
                    len(candidates) - len(selected),
                )

            for alert in selected:
                avg_bytes = await view.get_avg_daily_7d(alert.user_uuid)
                await gateway.mark_thresholds_alerted(
                    MarkThresholdsAlerted(
                        user_uuid=alert.user_uuid,
                        thresholds_gb=[
                            t for t in config.traffic_alert_thresholds_gb if t <= alert.threshold_gb
                        ],
                        alerted_at=now,
                    )
                )
                await gateway.mark_anomaly_alerted(
                    MarkAnomalyAlerted(user_uuid=alert.user_uuid, date=today)
                )
                text = format_threshold_alert(
                    username=alert.username,
                    total_bytes=alert.total_bytes,
                    threshold_gb=alert.threshold_gb,
                    critical_threshold_gb=config.traffic_critical_threshold_gb,
                    avg_daily_bytes=avg_bytes,
                    spike=is_spike(alert.total_bytes, avg_bytes, config.traffic_anomaly_multiplier),
                )
                await _send_to_admins(bot, config.admin_ids, alert, text)

            if selected:
                logger.info("Traffic check: %d threshold alerts sent", len(selected))


async def traffic_monitoring_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    bot: Bot,
) -> None:
    logger.info(
        "Traffic monitoring starting, first check in 15s, interval=%ds",
        config.traffic_check_interval_seconds,
    )
    await asyncio.sleep(15)  # Let bot start before first heavy fetch
    while True:
        try:
            await _run_traffic_check(config, session_factory, raw_client, bot)
        except Exception as e:
            logger.error("Traffic monitoring error: %s", e)
        await asyncio.sleep(config.traffic_check_interval_seconds)

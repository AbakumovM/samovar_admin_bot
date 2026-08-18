import asyncio
import html
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.users.adapters.gateway import PostgresUserTrafficGateway
from src.apps.users.adapters.view import PostgresUserTrafficView
from src.apps.users.domain.commands import (
    MarkAnomalyAlerted,
    UpdateLastSnapshot,
    UpsertDailyTraffic,
)
from src.config import Config

logger = logging.getLogger(__name__)

NotifyFn = Callable[[str], Coroutine[Any, Any, None]]


def _compute_delta(current: int, previous: int) -> int | None:
    """Return bytes consumed since last snapshot. None means counter was reset."""
    delta = current - previous
    if delta < 0:
        return None
    return delta


def _check_anomaly(
    bytes_today: int,
    avg_daily_bytes: float,
    threshold_bytes: int,
    multiplier: float,
) -> tuple[bool, bool]:
    """Return (is_high, is_spike). Independent checks — either triggers an alert.

    is_high: today > threshold_bytes (absolute — catches stable heavy users)
    is_spike: today > multiplier * avg (relative — catches sudden surges)
              Only fires when avg history exists (avg > 0).
    """
    is_high = bytes_today > threshold_bytes
    is_spike = avg_daily_bytes > 0 and bytes_today > multiplier * avg_daily_bytes
    return is_high, is_spike


def _fmt_bytes(b: int) -> str:
    gb = b / 1024**3
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = b / 1024**2
    return f"{mb:.1f} MB"


async def _fetch_all_users(raw_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    # Raw HTTP via /users/stream: the remnawave SDK's response models predate
    # panel API v3.2.3 (users no longer have `uuid`, only numeric `id`), and
    # /users/stream is the endpoint meant for full-collection traversal
    # (unlike offset-based /users, which the panel docs warn against using
    # for heavy pagination).
    users: list[dict[str, Any]] = []
    cursor: int | None = None
    size = 1000
    while True:
        params: dict[str, int] = {"size": size}
        if cursor is not None:
            params["cursor"] = cursor
        response = await raw_client.get("/users/stream", params=params)
        response.raise_for_status()
        page = response.json()["response"]
        batch = page["users"]
        active = [
            u
            for u in batch
            if str(u.get("status", "")).lower() == "active" and u.get("telegramId") is not None
        ]
        users.extend(active)
        if not page.get("hasMore"):
            break
        cursor = page["nextCursor"]
    return users


async def _run_traffic_check(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    notify: NotifyFn,
) -> None:
    now = datetime.now(UTC)
    today = now.date()  # UTC date — requires server/container to run in UTC (Docker default)
    threshold_bytes = int(config.traffic_anomaly_threshold_gb * 1024**3)

    users = await _fetch_all_users(raw_client)
    logger.info("Traffic check: %d active users to process", len(users))

    # Transaction 1: process user snapshots and daily traffic
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

    # Transaction 2: anomaly detection and alerts
    async with session_factory() as session:
        async with session.begin():
            gateway = PostgresUserTrafficGateway(session=session)
            view = PostgresUserTrafficView(session=session)

            candidates = await view.get_today_unalerted()
            anomaly_count = 0
            alert_limit = 10  # Prevent Telegram flood if threshold misconfigured
            for record in candidates:
                if anomaly_count >= alert_limit:
                    logger.warning(
                        "Traffic anomaly alert limit reached (%d), suppressing further alerts",
                        alert_limit,
                    )
                    break
                avg_bytes = await view.get_avg_daily_7d(record.user_uuid)
                is_high, is_spike = _check_anomaly(
                    bytes_today=record.bytes_consumed,
                    avg_daily_bytes=avg_bytes,
                    threshold_bytes=threshold_bytes,
                    multiplier=config.traffic_anomaly_multiplier,
                )
                if not is_high:
                    continue
                await gateway.mark_anomaly_alerted(
                    MarkAnomalyAlerted(user_uuid=record.user_uuid, date=today)
                )
                safe_username = html.escape(record.username)
                labels: list[str] = []
                if is_high:
                    labels.append(f"Высокое потребление (>{_fmt_bytes(threshold_bytes)}/день)")
                if is_spike:
                    multiplier_actual = record.bytes_consumed / avg_bytes
                    labels.append(
                        f"Резкий скачок ×{multiplier_actual:.1f} "
                        f"(обычно ~{_fmt_bytes(int(avg_bytes))}/день)"
                    )
                await notify(
                    f"⚠️ Аномальный трафик: <b>{safe_username}</b>\n"
                    f"Сегодня: {_fmt_bytes(record.bytes_consumed)}\n"
                    + "\n".join(f"• {label}" for label in labels)
                )
                anomaly_count += 1

            if anomaly_count:
                logger.info("Traffic check: %d anomalies detected", anomaly_count)


async def traffic_monitoring_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    notify: NotifyFn,
) -> None:
    logger.info(
        "Traffic monitoring starting, first check in 15s, interval=%ds",
        config.traffic_check_interval_seconds,
    )
    await asyncio.sleep(15)  # Let bot start before first heavy fetch
    while True:
        try:
            await _run_traffic_check(config, session_factory, raw_client, notify)
        except Exception as e:
            logger.error("Traffic monitoring error: %s", e)
        await asyncio.sleep(config.traffic_check_interval_seconds)

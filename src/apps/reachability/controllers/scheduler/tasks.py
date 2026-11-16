import asyncio
import html
import logging
import random
from datetime import UTC, datetime
from typing import Any

import httpx
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.reachability.adapters.gateway import PostgresReachabilityGateway
from src.apps.reachability.adapters.view import PostgresReachabilityView
from src.apps.reachability.controllers.scheduler.pass_runner import (
    PASS_KEY,
    PassResult,
    PointTracker,
    run_pass,
)
from src.apps.reachability.domain.models import IpState
from src.apps.reachability.domain.targets import resolve_addresses, select_hosts
from src.config import Config
from src.infrastructure.reachability.ssh_runner import (
    ProbePoint,
    run_local_probe,
    run_remote_probe,
)

logger = logging.getLogger(__name__)


class _SessionStateStore:
    def __init__(self, view: PostgresReachabilityView, gateway: PostgresReachabilityGateway):
        self._view = view
        self._gateway = gateway

    async def get(self, ips: list[str]) -> dict[str, IpState]:
        return await self._view.get_states(ips)

    async def save(
        self,
        state: IpState,
        last_results: dict[str, str | None],
        checked_at: datetime,
        changed: bool,
    ) -> None:
        await self._gateway.save_state(state, last_results, checked_at, changed)


async def _fetch(raw_client: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
    response = await raw_client.get(path)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("response", payload) if isinstance(payload, dict) else payload
    return list(data)


_PASS_FAILURES_TO_ALERT = 3


async def _send(bot: Bot, admin_ids: list[int], messages: list[str]) -> None:
    for text in messages:
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error("Failed to send reachability alert to admin %s: %s", admin_id, e)


async def execute_pass(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    bot: Bot,
    tracker: PointTracker,
) -> PassResult:
    hosts = await _fetch(raw_client, "/hosts")
    nodes = await _fetch(raw_client, "/nodes")
    tags = set(config.reachability_host_tags)
    addresses = {str(h["address"]) for h in select_hosts(hosts, tags)}
    resolved = await resolve_addresses(addresses | set(config.reachability_control_targets))
    control_targets = [
        {"ip": resolved[domain][0], "port": 443, "sni": domain}
        for domain in config.reachability_control_targets
        if domain in resolved
    ]
    points = [ProbePoint(name=p.name, host=p.host) for p in config.reachability_points]

    async def run_point(point: ProbePoint, payload: list[dict[str, Any]]) -> Any:
        return await run_remote_probe(
            point,
            payload,
            config.reachability_ssh_user,
            config.reachability_ssh_key_path,
            config.reachability_ssh_known_hosts_path,
            config.reachability_point_timeout_seconds,
        )

    async def run_outside(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await run_local_probe(payload, config.reachability_timeout_seconds)

    async with tracker.lock, session_factory() as session:
        async with session.begin():
            store = _SessionStateStore(
                PostgresReachabilityView(session=session),
                PostgresReachabilityGateway(session=session),
            )
            result = await run_pass(
                hosts=hosts,
                nodes=nodes,
                resolved=resolved,
                control_targets=control_targets,
                tags=tags,
                points=points,
                run_point=run_point,
                run_outside=run_outside,
                states=store,
                tracker=tracker,
                confirm_passes=config.reachability_confirm_passes,
                min_ok_ratio=config.reachability_control_min_ok_ratio,
                now=datetime.now(UTC),
            )

    await _send(bot, config.admin_ids, result.messages)
    logger.info(
        "Reachability pass: checked=%d not_ok=%d skipped=%s messages=%d",
        result.checked,
        result.not_ok,
        result.skipped,
        len(result.messages),
    )
    return result


async def run_scheduled_pass(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    bot: Bot,
    tracker: PointTracker,
) -> list[str]:
    """One scheduled pass; returns alerts about the checker itself failing/recovering."""
    try:
        await execute_pass(config, session_factory, raw_client, bot, tracker)
    except Exception as e:
        logger.error("Reachability pass error: %r", e)
        if tracker.observe(PASS_KEY, False, _PASS_FAILURES_TO_ALERT) == "down":
            return [
                "⚠️ Проверка блокировок падает с ошибкой "
                f"{_PASS_FAILURES_TO_ALERT} раза подряд: {html.escape(repr(e), quote=False)}"
            ]
        return []
    if tracker.observe(PASS_KEY, True, _PASS_FAILURES_TO_ALERT) == "up":
        return ["✅ Проверка блокировок снова работает"]
    return []


async def reachability_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    raw_client: httpx.AsyncClient,
    bot: Bot,
    tracker: PointTracker,
) -> None:
    if not config.reachability_enabled:
        logger.info("Reachability checks disabled (REACHABILITY_ENABLED=false)")
        return
    logger.info(
        "Reachability checks starting, interval=%ds ±%ds",
        config.reachability_interval_seconds,
        config.reachability_jitter_seconds,
    )
    await asyncio.sleep(20)  # Let bot start before the first pass
    while True:
        await _send(
            bot,
            config.admin_ids,
            await run_scheduled_pass(config, session_factory, raw_client, bot, tracker),
        )
        jitter = random.uniform(
            -config.reachability_jitter_seconds, config.reachability_jitter_seconds
        )
        await asyncio.sleep(max(60.0, config.reachability_interval_seconds + jitter))

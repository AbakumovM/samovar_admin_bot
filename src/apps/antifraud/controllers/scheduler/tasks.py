import asyncio
import dataclasses
import html
import ipaddress
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from remnawave import RemnawaveSDK
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.antifraud.adapters.gateway import PostgresAntifraudGateway
from src.apps.antifraud.adapters.view import PostgresAntifraudCooldownView
from src.apps.antifraud.application.interactor import AntifraudInteractor
from src.apps.antifraud.domain.models import (
    AggregatedIp,
    FlaggedUser,
    GroupingMode,
    IpSighting,
    NodeConnectionsResult,
    NodeUserConnections,
)
from src.config import Config
from src.infrastructure.geoip.asn import AsnResolver
from src.infrastructure.remnawave.user_cache import UserLookupCache
from src.infrastructure.samovarbot.client import (
    SamovarbotClient,
    block_user,
    check_no_active_payment,
)

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096
_DIGEST_SAFETY_MARGIN = 200
_MAX_IPS_SHOWN_PER_USER = 5
_MAX_USERS_SHOWN = 25


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class _IpWhitelist:
    def __init__(self, entries: list[str]) -> None:
        self._exact: set[str] = set()
        self._networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for raw in entries:
            entry = raw.strip()
            if not entry:
                continue
            if "/" in entry:
                self._networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                self._exact.add(str(ipaddress.ip_address(entry)))

    def is_empty(self) -> bool:
        return not self._exact and not self._networks

    def contains(self, ip_str: str) -> bool:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if str(ip) in self._exact:
            return True
        return any(ip in net for net in self._networks)


async def _list_node_uuids(sdk: RemnawaveSDK) -> list[tuple[str, str]]:
    nodes = await sdk.nodes.get_all_nodes()
    return [(str(n.uuid), str(n.name)) for n in nodes]


async def _trigger_connections_job(raw_client: httpx.AsyncClient, node_uuid: str) -> str:
    response = await raw_client.post(f"/connections/by-node/{node_uuid}")
    response.raise_for_status()
    return str(response.json()["response"]["jobId"])


async def _poll_connections_job(
    raw_client: httpx.AsyncClient,
    job_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    elapsed = 0.0
    while elapsed < timeout_seconds:
        response = await raw_client.get(f"/connections/by-node/{job_id}")
        response.raise_for_status()
        payload: dict[str, Any] = response.json()["response"]
        if payload["isCompleted"]:
            return payload
        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds
    return None


def _parse_user_connections(user_entry: dict[str, Any]) -> NodeUserConnections:
    # A node may (in principle) report the same IP twice with different
    # lastSeen timestamps — keep only the most recent sighting per IP.
    latest_seen: dict[str, datetime] = {}
    for ip_entry in user_entry.get("ips", []):
        ip = str(ip_entry["ip"])
        seen = _parse_iso(ip_entry["lastSeen"])
        if ip not in latest_seen or seen > latest_seen[ip]:
            latest_seen[ip] = seen
    sightings = tuple(IpSighting(ip=ip, last_seen=seen) for ip, seen in sorted(latest_seen.items()))
    return NodeUserConnections(user_id=int(user_entry["userId"]), ips=sightings)


async def _fetch_node_connections(
    raw_client: httpx.AsyncClient,
    node_uuid: str,
    node_name: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> NodeConnectionsResult:
    """Trigger + poll one node's connections job. Never raises — any failure
    mode (HTTP error, timeout, isFailed, success=false) becomes ok=False so
    the caller can skip this node without aborting the whole scan pass.
    """
    try:
        job_id = await _trigger_connections_job(raw_client, node_uuid)
    except Exception as e:
        return NodeConnectionsResult(
            node_uuid=node_uuid,
            node_name=node_name,
            ok=False,
            failure_reason=f"trigger failed: {e}",
        )

    try:
        payload = await _poll_connections_job(
            raw_client, job_id, poll_interval_seconds, timeout_seconds
        )
    except Exception as e:
        return NodeConnectionsResult(
            node_uuid=node_uuid,
            node_name=node_name,
            ok=False,
            failure_reason=f"poll failed: {e}",
        )

    if payload is None:
        return NodeConnectionsResult(
            node_uuid=node_uuid,
            node_name=node_name,
            ok=False,
            failure_reason=f"timed out after {timeout_seconds}s",
        )
    if payload.get("isFailed"):
        return NodeConnectionsResult(
            node_uuid=node_uuid, node_name=node_name, ok=False, failure_reason="job isFailed"
        )

    result = payload.get("result")
    if result is None or not result.get("success"):
        return NodeConnectionsResult(
            node_uuid=node_uuid,
            node_name=node_name,
            ok=False,
            failure_reason="result missing or success=false",
        )

    users = tuple(_parse_user_connections(u) for u in result.get("users", []))
    return NodeConnectionsResult(node_uuid=node_uuid, node_name=node_name, ok=True, users=users)


def _aggregate_ips_by_user(
    results: list[NodeConnectionsResult],
) -> dict[int, dict[str, AggregatedIp]]:
    """Union (not sum) IPs per user across all successful node results.

    Same IP seen on two nodes merges into one entry (node_names accumulates,
    last_seen takes the max) rather than counting twice.
    """
    aggregated: dict[int, dict[str, AggregatedIp]] = {}
    for node_result in results:
        if not node_result.ok:
            continue
        for user_conn in node_result.users:
            per_ip = aggregated.setdefault(user_conn.user_id, {})
            for sighting in user_conn.ips:
                existing = per_ip.get(sighting.ip)
                if existing is None:
                    per_ip[sighting.ip] = AggregatedIp(
                        ip=sighting.ip,
                        node_names=(node_result.node_name,),
                        last_seen=sighting.last_seen,
                    )
                else:
                    node_names = existing.node_names
                    if node_result.node_name not in node_names:
                        node_names = (*node_names, node_result.node_name)
                    per_ip[sighting.ip] = AggregatedIp(
                        ip=sighting.ip,
                        node_names=node_names,
                        last_seen=max(existing.last_seen, sighting.last_seen),
                    )
    return aggregated


def _filter_whitelisted_ips(
    aggregated: dict[int, dict[str, AggregatedIp]], whitelist: _IpWhitelist
) -> dict[int, dict[str, AggregatedIp]]:
    if whitelist.is_empty():
        return aggregated
    filtered: dict[int, dict[str, AggregatedIp]] = {}
    for uid, ip_map in aggregated.items():
        kept = {ip: agg for ip, agg in ip_map.items() if not whitelist.contains(ip)}
        if kept:
            filtered[uid] = kept
    return filtered


def _filter_recent_ips(
    aggregated: dict[int, dict[str, AggregatedIp]],
    now: datetime,
    recency_seconds: int,
) -> dict[int, dict[str, AggregatedIp]]:
    """Drop IPs whose last_seen is older than recency_seconds.

    Xray-core's online-IP tracking on the node accumulates sightings over a
    window that in practice can span tens of minutes (observed live), not
    "concurrent right now" — this filter enforces our own notion of
    concurrency instead of relying on Xray's internal eviction timing.
    """
    filtered: dict[int, dict[str, AggregatedIp]] = {}
    for uid, ip_map in aggregated.items():
        recent = {
            ip: agg
            for ip, agg in ip_map.items()
            if (now - agg.last_seen).total_seconds() <= recency_seconds
        }
        if recent:
            filtered[uid] = recent
    return filtered


def _resolve_asn(
    aggregated: dict[int, dict[str, AggregatedIp]], resolver: AsnResolver
) -> dict[int, dict[str, AggregatedIp]]:
    """Annotate each AggregatedIp with ASN info. Cheap no-op when resolver is
    NopAsnResolver (MaxMind not configured) — always run so IP-mode digests
    can still show a "(N ASN)" hint if a database happens to be available.
    """
    resolved: dict[int, dict[str, AggregatedIp]] = {}
    for uid, ip_map in aggregated.items():
        new_map: dict[str, AggregatedIp] = {}
        for ip, agg in ip_map.items():
            info = resolver.lookup(ip)
            if info is not None:
                agg = AggregatedIp(
                    ip=agg.ip,
                    node_names=agg.node_names,
                    last_seen=agg.last_seen,
                    asn=info.number,
                    asn_org=info.org,
                )
            new_map[ip] = agg
        resolved[uid] = new_map
    return resolved


def _grouping_mode(config: Config) -> GroupingMode:
    if config.antifraud_asn_grouping:
        return "asn"
    if config.antifraud_subnet_grouping:
        return "subnet"
    return "ip"


def _subnet_prefix(ip_str: str, prefix_v4: int) -> str:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return ip_str
    if isinstance(ip, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{ip}/{prefix_v4}", strict=False))
    return str(ip)  # IPv6 counted per-address, matching remnawave-limiter


def _compute_group_count(
    ip_map: dict[str, AggregatedIp], mode: GroupingMode, subnet_prefix_v4: int
) -> int:
    if mode == "asn":
        seen_asn: set[int] = set()
        unknown = 0
        for agg in ip_map.values():
            if agg.asn is None:
                unknown += 1
            else:
                seen_asn.add(agg.asn)
        return len(seen_asn) + unknown
    if mode == "subnet":
        seen_subnets = {_subnet_prefix(agg.ip, subnet_prefix_v4) for agg in ip_map.values()}
        return len(seen_subnets)
    return len(ip_map)


def _node_prefix(node_name: str) -> str:
    return node_name.split("-")[0] if "-" in node_name else node_name


def _ru_node_group_count(
    ips: tuple[AggregatedIp, ...],
    mode: GroupingMode,
    subnet_prefix_v4: int,
    ru_prefixes: set[str],
) -> int:
    ru_only = {
        agg.ip: agg
        for agg in ips
        if any(_node_prefix(name) in ru_prefixes for name in agg.node_names)
    }
    return _compute_group_count(ru_only, mode, subnet_prefix_v4)


def _resolve_and_filter_candidates(
    aggregated: dict[int, dict[str, AggregatedIp]],
    user_index: dict[int, dict[str, Any]],
    config: Config,
) -> tuple[list[FlaggedUser], list[FlaggedUser]]:
    """Returns (hard, soft).

    hard: group_count > limit + slack + floor(limit * multiplier) — triggers
    the full violation-accumulation/cooldown/digest/drop-button flow.
    soft: limit < group_count <= hard_threshold, only returned when
    antifraud_soft_alerts_enabled — informational only, no action, separate
    cooldown, does not feed the violation counter.

    hwidDeviceLimit semantics: null (never configured) and 0 (explicit
    "unlimited" — product decision, matches remnawave-limiter's convention
    rather than the panel's own HWID-registration-gate semantics for 0)
    both skip the user entirely.
    """
    whitelist_user_ids = set(config.antifraud_whitelist_user_ids)
    mode = _grouping_mode(config)
    hard: list[FlaggedUser] = []
    soft: list[FlaggedUser] = []

    for uid, ip_map in aggregated.items():
        if uid in whitelist_user_ids:
            continue
        record = user_index.get(uid)
        if record is None:
            logger.warning(
                "Antifraud: candidate user_id=%d not resolvable via /users/{id}, skipping", uid
            )
            continue
        device_limit_raw = record.get("hwidDeviceLimit")
        if device_limit_raw is None or device_limit_raw == 0:
            continue
        device_limit = int(device_limit_raw)

        group_count = _compute_group_count(ip_map, mode, config.antifraud_subnet_prefix_v4)
        if group_count <= device_limit:
            continue

        hard_threshold = (
            device_limit
            + config.antifraud_ip_slack
            + int(device_limit * config.antifraud_ip_slack_multiplier)
        )
        ips_sorted = tuple(sorted(ip_map.values(), key=lambda a: a.last_seen, reverse=True))
        username = str(record.get("username", f"id:{uid}"))
        telegram_id = record.get("telegramId")

        if group_count > hard_threshold:
            hard.append(
                FlaggedUser(
                    remnawave_id=uid,
                    username=username,
                    telegram_id=telegram_id,
                    ip_count=len(ip_map),
                    group_count=group_count,
                    grouping_mode=mode,
                    ips=ips_sorted,
                    hwid_device_limit=device_limit,
                    threshold=hard_threshold,
                    is_hard=True,
                )
            )
        elif config.antifraud_soft_alerts_enabled:
            soft.append(
                FlaggedUser(
                    remnawave_id=uid,
                    username=username,
                    telegram_id=telegram_id,
                    ip_count=len(ip_map),
                    group_count=group_count,
                    grouping_mode=mode,
                    ips=ips_sorted,
                    hwid_device_limit=device_limit,
                    threshold=hard_threshold,
                    is_hard=False,
                )
            )

    hard.sort(key=lambda f: f.group_count - f.threshold, reverse=True)
    soft.sort(key=lambda f: f.group_count - f.threshold, reverse=True)
    return hard, soft


def _format_grouping_line(f: FlaggedUser) -> str:
    if f.grouping_mode == "asn":
        base = f"лимит: {f.hwid_device_limit} | ASN: {f.group_count} | IP: {f.ip_count}"
    elif f.grouping_mode == "subnet" and f.group_count < f.ip_count:
        base = f"лимит: {f.hwid_device_limit} | подсетей: {f.group_count} | IP: {f.ip_count}"
    else:
        base = f"лимит: {f.hwid_device_limit} | IP: {f.ip_count}"
    if f.grouping_mode != "asn":
        unique_asn = len({ip.asn for ip in f.ips if ip.asn is not None})
        if unique_asn > 0:
            base += f" ({unique_asn} ASN)"
    return base + f", порог: {f.threshold}"


def _format_criteria_line(f: FlaggedUser) -> str:
    if f.no_active_payment is True:
        payment_str = "нет активной оплаты ⚠️"
    elif f.no_active_payment is False:
        payment_str = "оплата активна"
    else:
        payment_str = "оплата: не проверялась"
    ru_str = f"RU-ноды: {f.ru_node_ip_count} (порог {f.ru_node_threshold})"
    if f.ru_node_ip_count > f.ru_node_threshold:
        ru_str += " ⚠️"
    return f"  {ru_str} | {payment_str} | критериев: {f.criteria_matched}/3"


def _format_ip_line(ip: AggregatedIp) -> str:
    href = f"https://ipinfo.io/{ip.ip}"
    ip_link = f'<a href="{html.escape(href)}">{html.escape(ip.ip)}</a>'
    org_part = f" — {html.escape(ip.asn_org)}" if ip.asn_org else ""
    return (
        f"   {ip_link}{org_part} — {html.escape(', '.join(ip.node_names))} — "
        f"{ip.last_seen.strftime('%H:%M:%S UTC')}"
    )


def _format_digest(flagged: list[FlaggedUser], *, hard: bool) -> str:
    if hard:
        header = (
            f"🕵️ Antifraud: обнаружено пользователей с подозрением на шеринг: "
            f"<b>{len(flagged)}</b>\n\n"
        )
    else:
        header = (
            f"ℹ️ Antifraud: пользователи около лимита устройств (информационно, "
            f"без действий): <b>{len(flagged)}</b>\n\n"
        )
    lines: list[str] = [header]
    budget = TELEGRAM_MESSAGE_LIMIT - _DIGEST_SAFETY_MARGIN
    shown = 0
    used = len(header)

    for f in flagged:
        if shown >= _MAX_USERS_SHOWN:
            break
        examples = f.ips[:_MAX_IPS_SHOWN_PER_USER]
        ip_lines = "\n".join(_format_ip_line(ip) for ip in examples)
        if len(f.ips) > _MAX_IPS_SHOWN_PER_USER:
            ip_lines += f"\n   +{len(f.ips) - _MAX_IPS_SHOWN_PER_USER} ещё"
        tg_str = f"tg:{f.telegram_id}" if f.telegram_id is not None else "нет telegram_id"
        criteria_part = f"\n{_format_criteria_line(f)}" if hard else ""
        entry = (
            f"• <b>{html.escape(f.username)}</b> ({tg_str})\n"
            f"  {_format_grouping_line(f)}{criteria_part}\n"
            f"{ip_lines}\n"
        )
        if used + len(entry) > budget:
            break
        lines.append(entry)
        used += len(entry)
        shown += 1

    if shown < len(flagged):
        lines.append(f"\n… и ещё {len(flagged) - shown} пользователь(ей) не показано.")

    return "".join(lines)


def _format_auto_block_digest(blocked: list[FlaggedUser]) -> str:
    header = f"🚫 Antifraud: автоматически заблокировано пользователей: <b>{len(blocked)}</b>\n\n"
    lines = [header]
    for f in blocked:
        tg_str = f"tg:{f.telegram_id}"
        lines.append(
            f"• <b>{html.escape(f.username)}</b> ({tg_str})\n"
            f"  {_format_grouping_line(f)}\n{_format_criteria_line(f)}\n"
        )
    return "".join(lines)


def _make_digest_keyboard(flagged: list[FlaggedUser]) -> InlineKeyboardMarkup:
    rows = []
    for f in flagged[:_MAX_USERS_SHOWN]:
        if f.telegram_id is None:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"antifraud_block:{f.remnawave_id}:{f.telegram_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _resolve_user(
    raw_client: httpx.AsyncClient, cache: UserLookupCache, user_id: int
) -> dict[str, Any] | None:
    cached = cache.get(user_id)
    if cached is not None:
        return cached
    response = await raw_client.get(f"/users/{user_id}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    record: dict[str, Any] = response.json()["response"]
    cache.set(user_id, record)
    return record


async def _resolve_users_bounded(
    raw_client: httpx.AsyncClient,
    cache: UserLookupCache,
    user_ids: list[int],
    concurrency: int,
) -> dict[int, dict[str, Any]]:
    """Resolve many candidates concurrently, bounded by a semaphore.

    A busy panel can have thousands of concurrently-online users — doing one
    sequential GET /users/{id} round-trip each (observed live: ~1.5 req/s)
    would take longer than the scan interval itself. Bounded concurrency
    (default 8, matching remnawave-limiter's own worker-pool size for the
    same problem) keeps this well within budget without hammering the panel.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(uid: int) -> tuple[int, dict[str, Any] | None]:
        async with semaphore:
            return uid, await _resolve_user(raw_client, cache, uid)

    resolved = await asyncio.gather(*(_bounded(uid) for uid in user_ids))
    return {uid: record for uid, record in resolved if record is not None}


async def _resolve_payment_bounded(
    client: SamovarbotClient, telegram_ids: list[int], concurrency: int
) -> dict[int, bool | None]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(tg_id: int) -> tuple[int, bool | None]:
        async with semaphore:
            return tg_id, await check_no_active_payment(client, tg_id)

    resolved = await asyncio.gather(*(_bounded(tg_id) for tg_id in telegram_ids))
    return dict(resolved)


async def _enrich_hard_with_new_criteria(
    hard: list[FlaggedUser],
    config: Config,
    samovarbot_client: SamovarbotClient,
) -> list[FlaggedUser]:
    """Добавляет критерии RU-нод и статуса оплаты уже-hard кандидатам.

    criteria_matched стартует с 1 (is_hard — это критерий 2, всегда true
    для любого из списка hard) и получает +1 за каждый дополнительный
    сработавший критерий. Критерий, который не удалось оценить (нет
    telegram_id, samovarbot недоступен), даёт 0, никогда не завышая счёт
    на недостающих данных.
    """
    ru_prefixes = {p.upper() for p in config.antifraud_ru_node_prefixes}
    interim: list[FlaggedUser] = []
    for f in hard:
        ru_count = _ru_node_group_count(
            f.ips, f.grouping_mode, config.antifraud_subnet_prefix_v4, ru_prefixes
        )
        ru_tripped = ru_count > config.antifraud_ru_node_ip_threshold
        interim.append(
            dataclasses.replace(
                f,
                ru_node_ip_count=ru_count,
                ru_node_threshold=config.antifraud_ru_node_ip_threshold,
                criteria_matched=1 + (1 if ru_tripped else 0),
            )
        )

    payment_targets = [f.telegram_id for f in interim if f.telegram_id is not None]
    payment_by_tg = await _resolve_payment_bounded(
        samovarbot_client, payment_targets, config.antifraud_user_resolve_concurrency
    )

    enriched: list[FlaggedUser] = []
    for f in interim:
        no_payment = payment_by_tg.get(f.telegram_id) if f.telegram_id is not None else None
        enriched.append(
            dataclasses.replace(
                f,
                no_active_payment=no_payment,
                criteria_matched=f.criteria_matched + (1 if no_payment else 0),
            )
        )
    return enriched


async def _drop_connections(raw_client: httpx.AsyncClient, remnawave_id: int) -> bool:
    try:
        response = await raw_client.post(
            "/connections/drop",
            json={
                "dropBy": {"by": "userIds", "userIds": [remnawave_id]},
                "targetNodes": {"target": "allNodes"},
            },
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("Antifraud: drop-connections failed for %d: %s", remnawave_id, e)
        return False


async def _run_antifraud_scan(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    sdk: RemnawaveSDK,
    raw_client: httpx.AsyncClient,
    bot: Bot,
    user_cache: UserLookupCache,
    asn_resolver: AsnResolver,
    samovarbot_client: SamovarbotClient,
) -> int:
    """Run one full scan pass. Returns how many users were actually notified
    on the hard (action-eligible) track this run — used by both the
    background loop and the on-demand /antifraud_check command to report a
    result. Soft (informational) notifications are logged but not counted.
    """
    now = datetime.now(UTC)

    ignored = {u.lower() for u in config.antifraud_ignored_node_uuids}
    all_nodes = await _list_node_uuids(sdk)
    nodes = [(uuid, name) for uuid, name in all_nodes if uuid.lower() not in ignored]
    logger.info(
        "Antifraud scan: polling %d nodes sequentially (%d ignored)",
        len(nodes),
        len(all_nodes) - len(nodes),
    )

    results: list[NodeConnectionsResult] = []
    for node_uuid, node_name in nodes:
        result = await _fetch_node_connections(
            raw_client,
            node_uuid,
            node_name,
            poll_interval_seconds=config.antifraud_job_poll_interval_seconds,
            timeout_seconds=config.antifraud_job_poll_timeout_seconds,
        )
        if not result.ok:
            logger.warning(
                "Antifraud: skipping node %s (%s): %s",
                node_name,
                node_uuid,
                result.failure_reason,
            )
        results.append(result)

    aggregated = _aggregate_ips_by_user(results)
    aggregated = _filter_whitelisted_ips(aggregated, _IpWhitelist(config.antifraud_ip_whitelist))
    aggregated = _filter_recent_ips(aggregated, now, config.antifraud_ip_recency_seconds)
    if not aggregated:
        logger.info("Antifraud scan: no users with recent concurrent IPs")
        return 0

    aggregated = _resolve_asn(aggregated, asn_resolver)

    logger.info("Antifraud scan: %d users online, resolving via /users/{id}", len(aggregated))
    user_index = await _resolve_users_bounded(
        raw_client,
        user_cache,
        list(aggregated.keys()),
        config.antifraud_user_resolve_concurrency,
    )

    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, config)
    if not hard and not soft:
        logger.info("Antifraud scan: no candidates above device limit")
        return 0

    notified_count = 0
    async with session_factory() as session:
        async with session.begin():
            interactor = AntifraudInteractor(
                gateway=PostgresAntifraudGateway(session=session),
                view=PostgresAntifraudCooldownView(session=session),
            )

            if hard:
                hard = await _enrich_hard_with_new_criteria(hard, config, samovarbot_client)
                accumulated_ids = await interactor.filter_by_violation_threshold(
                    remnawave_ids=[f.remnawave_id for f in hard],
                    now=now,
                    threshold=config.antifraud_violation_threshold,
                    window_seconds=config.antifraud_violation_window_seconds,
                )
                past_threshold = [f for f in hard if f.remnawave_id in accumulated_ids]
                if past_threshold:
                    eligible_ids = await interactor.filter_out_cooled_down(
                        remnawave_ids=[f.remnawave_id for f in past_threshold],
                        now=now,
                        cooldown_hours=config.antifraud_cooldown_hours,
                    )
                    to_notify = [f for f in past_threshold if f.remnawave_id in eligible_ids]
                    if to_notify:
                        auto_block_ids = {
                            f.remnawave_id
                            for f in to_notify
                            if f.criteria_matched == 3
                            and config.antifraud_auto_block_enabled
                            and f.telegram_id is not None
                        }
                        auto_blocked: list[FlaggedUser] = []
                        manual: list[FlaggedUser] = []
                        for f in to_notify:
                            if f.remnawave_id not in auto_block_ids:
                                manual.append(f)
                                continue
                            assert f.telegram_id is not None
                            reason = f"antifraud: auto-block, {f.criteria_matched}/3 критериев"
                            blocked = await block_user(samovarbot_client, f.telegram_id, reason)
                            if blocked:
                                await _drop_connections(raw_client, f.remnawave_id)
                                auto_blocked.append(f)
                            else:
                                logger.error(
                                    "Antifraud: auto-block failed for tg:%d, "
                                    "falling back to manual alert",
                                    f.telegram_id,
                                )
                                manual.append(f)

                        if auto_blocked:
                            auto_digest = _format_auto_block_digest(auto_blocked)
                            for admin_id in config.admin_ids:
                                try:
                                    await bot.send_message(admin_id, auto_digest)
                                except Exception as e:
                                    logger.error(
                                        "Antifraud: failed to notify admin %s: %s", admin_id, e
                                    )
                        if manual:
                            digest = _format_digest(manual, hard=True)
                            keyboard = _make_digest_keyboard(manual)
                            for admin_id in config.admin_ids:
                                try:
                                    await bot.send_message(admin_id, digest, reply_markup=keyboard)
                                except Exception as e:
                                    logger.error(
                                        "Antifraud: failed to notify admin %s: %s", admin_id, e
                                    )
                        await interactor.mark_notified_batch(
                            remnawave_ids=[f.remnawave_id for f in to_notify], now=now
                        )
                        notified_count = len(to_notify)
                        logger.info(
                            "Antifraud scan: notified about %d/%d hard-flagged users "
                            "(%d auto-blocked)",
                            len(to_notify),
                            len(hard),
                            len(auto_blocked),
                        )

            if soft:
                eligible_soft_ids = await interactor.filter_out_cooled_down_soft(
                    remnawave_ids=[f.remnawave_id for f in soft],
                    now=now,
                    cooldown_hours=config.antifraud_cooldown_hours,
                )
                to_notify_soft = [f for f in soft if f.remnawave_id in eligible_soft_ids]
                if to_notify_soft:
                    soft_digest = _format_digest(to_notify_soft, hard=False)
                    for admin_id in config.admin_ids:
                        try:
                            await bot.send_message(admin_id, soft_digest)
                        except Exception as e:
                            logger.error(
                                "Antifraud: failed to send soft alert to admin %s: %s", admin_id, e
                            )
                    await interactor.mark_soft_notified_batch(
                        remnawave_ids=[f.remnawave_id for f in to_notify_soft], now=now
                    )
                    logger.info(
                        "Antifraud scan: sent soft alert about %d/%d users",
                        len(to_notify_soft),
                        len(soft),
                    )

    return notified_count


async def antifraud_scan_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    sdk: RemnawaveSDK,
    raw_client: httpx.AsyncClient,
    bot: Bot,
    user_cache: UserLookupCache,
    asn_resolver: AsnResolver,
    samovarbot_client: SamovarbotClient,
) -> None:
    if not config.antifraud_enabled:
        logger.info("Antifraud scan disabled (antifraud_enabled=false), task exiting")
        return
    logger.info(
        "Antifraud scan starting, first check in 30s, interval=%ds",
        config.antifraud_scan_interval_seconds,
    )
    await asyncio.sleep(30)
    while True:
        try:
            await _run_antifraud_scan(
                config,
                session_factory,
                sdk,
                raw_client,
                bot,
                user_cache,
                asn_resolver,
                samovarbot_client,
            )
        except Exception as e:
            logger.error("Antifraud scan error: %s", e)
        await asyncio.sleep(config.antifraud_scan_interval_seconds)

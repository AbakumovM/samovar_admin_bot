from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from src.apps.antifraud.controllers.scheduler.tasks import (
    TELEGRAM_MESSAGE_LIMIT,
    _aggregate_ips_by_user,
    _compute_group_count,
    _drop_connections,
    _enrich_hard_with_new_criteria,
    _filter_recent_ips,
    _filter_whitelisted_ips,
    _format_auto_block_digest,
    _format_criteria_breakdown,
    _format_digest,
    _grouping_mode,
    _IpWhitelist,
    _make_digest_keyboard,
    _mark_blocked_in_keyboard,
    _node_prefix,
    _resolve_and_filter_candidates,
    _resolve_asn,
    _resolve_payment_bounded,
    _ru_node_group_count,
    _subnet_prefix,
)
from src.apps.antifraud.domain.models import (
    AggregatedIp,
    FlaggedUser,
    IpSighting,
    NodeConnectionsResult,
    NodeUserConnections,
)
from src.config import Config
from src.infrastructure.geoip.asn import AsnInfo

_T1 = datetime(2026, 8, 18, 17, 36, 22, tzinfo=UTC)
_T2 = datetime(2026, 8, 18, 17, 37, 45, tzinfo=UTC)


def make_config(**overrides: object) -> Config:
    base: dict[str, object] = {
        "telegram_bot_token": "x",
        "admin_ids": [1],
        "remnawave_base_url": "https://x",
        "remnawave_token": "x",
        "database_url": "postgresql+asyncpg://a:b@c/d",
        "antifraud_ip_slack": 2,
        "antifraud_ip_slack_multiplier": 0.0,
        "antifraud_soft_alerts_enabled": False,
        "antifraud_whitelist_user_ids": [],
        "antifraud_subnet_grouping": False,
        "antifraud_asn_grouping": False,
        "antifraud_subnet_prefix_v4": 24,
    }
    base.update(overrides)
    return Config(_env_file=None, **base)  # type: ignore[call-arg,arg-type]


def make_result(
    *, node_uuid: str = "node-1", ok: bool = True, users: tuple[NodeUserConnections, ...] = ()
) -> NodeConnectionsResult:
    return NodeConnectionsResult(
        node_uuid=node_uuid, node_name=f"name-{node_uuid}", ok=ok, users=users
    )


def make_flagged(
    *,
    remnawave_id: int = 1,
    username: str = "user1",
    ip_count: int = 8,
    group_count: int | None = None,
    grouping_mode: str = "ip",
    threshold: int = 5,
    ips: tuple[AggregatedIp, ...] = (
        AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1),
        AggregatedIp(ip="2.2.2.2", node_names=("DE-1",), last_seen=_T2),
    ),
    telegram_id: int | None = 123,
    hwid_device_limit: int = 3,
    is_hard: bool = True,
    ru_node_ip_count: int = 0,
    ru_node_threshold: int = 0,
    no_active_payment: bool | None = None,
    criteria_matched: int = 0,
) -> FlaggedUser:
    return FlaggedUser(
        remnawave_id=remnawave_id,
        username=username,
        telegram_id=telegram_id,
        ip_count=ip_count,
        group_count=group_count if group_count is not None else ip_count,
        grouping_mode=grouping_mode,  # type: ignore[arg-type]
        ips=ips,
        hwid_device_limit=hwid_device_limit,
        threshold=threshold,
        is_hard=is_hard,
        ru_node_ip_count=ru_node_ip_count,
        ru_node_threshold=ru_node_threshold,
        no_active_payment=no_active_payment,
        criteria_matched=criteria_matched,
    )


def _agg_ips(count: int) -> dict[str, AggregatedIp]:
    return {
        f"1.1.1.{i}": AggregatedIp(ip=f"1.1.1.{i}", node_names=("DE-1",), last_seen=_T1)
        for i in range(count)
    }


# ---- aggregation ----


def test_aggregate_ips_by_user_unions_across_nodes() -> None:
    results = [
        make_result(
            node_uuid="n1",
            users=(NodeUserConnections(user_id=1, ips=(IpSighting(ip="1.1.1.1", last_seen=_T1),)),),
        ),
        make_result(
            node_uuid="n2",
            users=(NodeUserConnections(user_id=1, ips=(IpSighting(ip="2.2.2.2", last_seen=_T2),)),),
        ),
    ]
    aggregated = _aggregate_ips_by_user(results)
    assert set(aggregated[1].keys()) == {"1.1.1.1", "2.2.2.2"}


def test_aggregate_ips_by_user_same_ip_two_nodes_merges_node_names() -> None:
    results = [
        make_result(
            node_uuid="n1",
            users=(NodeUserConnections(user_id=1, ips=(IpSighting(ip="1.1.1.1", last_seen=_T1),)),),
        ),
        make_result(
            node_uuid="n2",
            users=(NodeUserConnections(user_id=1, ips=(IpSighting(ip="1.1.1.1", last_seen=_T2),)),),
        ),
    ]
    aggregated = _aggregate_ips_by_user(results)
    assert len(aggregated[1]) == 1
    entry = aggregated[1]["1.1.1.1"]
    assert set(entry.node_names) == {"name-n1", "name-n2"}
    assert entry.last_seen == _T2  # max of the two sightings


def test_aggregate_ips_by_user_skips_failed_nodes() -> None:
    results = [
        make_result(
            node_uuid="n1",
            ok=False,
            users=(NodeUserConnections(user_id=1, ips=(IpSighting(ip="1.1.1.1", last_seen=_T1),)),),
        ),
        make_result(
            node_uuid="n2",
            ok=True,
            users=(NodeUserConnections(user_id=2, ips=(IpSighting(ip="2.2.2.2", last_seen=_T2),)),),
        ),
    ]
    aggregated = _aggregate_ips_by_user(results)
    assert 1 not in aggregated
    assert set(aggregated[2].keys()) == {"2.2.2.2"}


# ---- IP whitelist ----


def test_ip_whitelist_matches_exact_ip() -> None:
    wl = _IpWhitelist(["1.1.1.1"])
    assert wl.contains("1.1.1.1") is True
    assert wl.contains("1.1.1.2") is False


def test_ip_whitelist_matches_cidr() -> None:
    wl = _IpWhitelist(["10.0.0.0/8"])
    assert wl.contains("10.1.2.3") is True
    assert wl.contains("11.0.0.0") is False


def test_ip_whitelist_empty_matches_nothing() -> None:
    wl = _IpWhitelist([])
    assert wl.is_empty() is True
    assert wl.contains("1.1.1.1") is False


def test_filter_whitelisted_ips_drops_matching_and_keeps_others() -> None:
    aggregated = {
        1: {
            "1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1),
            "2.2.2.2": AggregatedIp(ip="2.2.2.2", node_names=("DE-1",), last_seen=_T1),
        }
    }
    filtered = _filter_whitelisted_ips(aggregated, _IpWhitelist(["1.1.1.1"]))
    assert set(filtered[1].keys()) == {"2.2.2.2"}


def test_filter_whitelisted_ips_drops_user_if_all_whitelisted() -> None:
    aggregated = {1: {"1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1)}}
    filtered = _filter_whitelisted_ips(aggregated, _IpWhitelist(["1.1.1.1"]))
    assert filtered == {}


# ---- recency filter ----


def test_filter_recent_ips_drops_stale_entries() -> None:
    now = datetime(2026, 8, 19, 12, 20, 0, tzinfo=UTC)
    stale = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)  # 20 minutes old
    recent = datetime(2026, 8, 19, 12, 19, 50, tzinfo=UTC)  # 10 seconds old
    aggregated = {
        1: {
            "1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=stale),
            "2.2.2.2": AggregatedIp(ip="2.2.2.2", node_names=("DE-1",), last_seen=recent),
        }
    }
    filtered = _filter_recent_ips(aggregated, now, recency_seconds=60)
    assert set(filtered[1].keys()) == {"2.2.2.2"}


def test_filter_recent_ips_drops_user_entirely_if_all_stale() -> None:
    now = datetime(2026, 8, 19, 12, 20, 0, tzinfo=UTC)
    stale = datetime(2026, 8, 19, 11, 0, 0, tzinfo=UTC)
    aggregated = {1: {"1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=stale)}}
    filtered = _filter_recent_ips(aggregated, now, recency_seconds=60)
    assert filtered == {}


def test_filter_recent_ips_boundary_inclusive() -> None:
    now = datetime(2026, 8, 19, 12, 20, 0, tzinfo=UTC)
    exactly_60s_ago = datetime(2026, 8, 19, 12, 19, 0, tzinfo=UTC)
    aggregated = {
        1: {"1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=exactly_60s_ago)}
    }
    filtered = _filter_recent_ips(aggregated, now, recency_seconds=60)
    assert set(filtered[1].keys()) == {"1.1.1.1"}


# ---- ASN resolution ----


class _StubResolver:
    def __init__(self, mapping: dict[str, AsnInfo]) -> None:
        self._mapping = mapping

    def lookup(self, ip: str) -> AsnInfo | None:
        return self._mapping.get(ip)


def test_resolve_asn_annotates_known_ips() -> None:
    aggregated = {1: {"1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1)}}
    resolver = _StubResolver({"1.1.1.1": AsnInfo(number=13335, org="Cloudflare")})
    resolved = _resolve_asn(aggregated, resolver)
    assert resolved[1]["1.1.1.1"].asn == 13335
    assert resolved[1]["1.1.1.1"].asn_org == "Cloudflare"


def test_resolve_asn_leaves_unknown_ips_unannotated() -> None:
    aggregated = {1: {"1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1)}}
    resolved = _resolve_asn(aggregated, _StubResolver({}))
    assert resolved[1]["1.1.1.1"].asn is None


# ---- grouping mode selection ----


def test_grouping_mode_defaults_to_ip() -> None:
    assert _grouping_mode(make_config()) == "ip"


def test_grouping_mode_subnet_when_enabled() -> None:
    assert _grouping_mode(make_config(antifraud_subnet_grouping=True)) == "subnet"


def test_grouping_mode_asn_takes_priority_over_subnet() -> None:
    cfg = make_config(antifraud_subnet_grouping=True, antifraud_asn_grouping=True)
    assert _grouping_mode(cfg) == "asn"


def test_subnet_prefix_groups_ipv4_by_24() -> None:
    assert _subnet_prefix("1.2.3.4", 24) == "1.2.3.0/24"
    assert _subnet_prefix("1.2.3.200", 24) == "1.2.3.0/24"


def test_subnet_prefix_ipv6_counted_per_address() -> None:
    assert _subnet_prefix("2001:db8::1", 24) == "2001:db8::1"


def test_compute_group_count_ip_mode_counts_raw_ips() -> None:
    assert _compute_group_count(_agg_ips(5), "ip", 24) == 5


def test_compute_group_count_subnet_mode_collapses_same_subnet() -> None:
    ip_map = {
        "1.2.3.1": AggregatedIp(ip="1.2.3.1", node_names=("DE-1",), last_seen=_T1),
        "1.2.3.2": AggregatedIp(ip="1.2.3.2", node_names=("DE-1",), last_seen=_T1),
        "5.6.7.8": AggregatedIp(ip="5.6.7.8", node_names=("DE-1",), last_seen=_T1),
    }
    assert _compute_group_count(ip_map, "subnet", 24) == 2


def test_compute_group_count_asn_mode_collapses_same_asn() -> None:
    ip_map = {
        "1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1, asn=13335),
        "1.1.1.2": AggregatedIp(ip="1.1.1.2", node_names=("DE-1",), last_seen=_T1, asn=13335),
        "8.8.8.8": AggregatedIp(ip="8.8.8.8", node_names=("DE-1",), last_seen=_T1, asn=15169),
    }
    assert _compute_group_count(ip_map, "asn", 24) == 2


def test_compute_group_count_asn_mode_unknown_asn_counted_individually() -> None:
    ip_map = {
        "1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1, asn=None),
        "1.1.1.2": AggregatedIp(ip="1.1.1.2", node_names=("DE-1",), last_seen=_T1, asn=None),
    }
    assert _compute_group_count(ip_map, "asn", 24) == 2


# ---- resolve + filter candidates (hard/soft, whitelist, limit semantics) ----


def test_resolve_and_filter_candidates_threshold_is_exclusive() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 3}}
    # exactly at threshold (3 + slack 2 = 5) — not flagged
    aggregated = {1: _agg_ips(5)}
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert hard == []
    assert soft == []


def test_resolve_and_filter_candidates_above_threshold_flags_hard() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 3}}
    aggregated = {1: _agg_ips(6)}
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert soft == []
    assert len(hard) == 1
    assert hard[0].ip_count == 6
    assert hard[0].group_count == 6
    assert hard[0].threshold == 5
    assert hard[0].hwid_device_limit == 3
    assert hard[0].is_hard is True


def test_resolve_and_filter_candidates_null_limit_skipped() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": None}}
    aggregated = {1: _agg_ips(50)}
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert hard == []
    assert soft == []


def test_resolve_and_filter_candidates_zero_limit_treated_as_unlimited_skipped() -> None:
    # Product decision: 0 = unlimited (matches remnawave-limiter's convention,
    # not the panel's own HWID-registration-gate semantics for 0).
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 0}}
    aggregated = {1: _agg_ips(50)}
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert hard == []
    assert soft == []


def test_resolve_and_filter_candidates_missing_user_id_skipped() -> None:
    aggregated = {1: _agg_ips(10), 2: _agg_ips(10)}
    user_index = {2: {"username": "u2", "telegramId": 456, "hwidDeviceLimit": 1}}
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert len(hard) == 1
    assert hard[0].remnawave_id == 2


def test_resolve_and_filter_candidates_handles_null_telegram_id() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 1}}
    aggregated = {1: _agg_ips(4)}
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert len(hard) == 1
    assert hard[0].telegram_id is None


def test_resolve_and_filter_candidates_sorted_descending_by_excess() -> None:
    user_index = {
        1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 1},  # threshold 3
        2: {"username": "u2", "telegramId": None, "hwidDeviceLimit": 1},  # threshold 3
    }
    aggregated = {
        1: _agg_ips(4),  # excess 1
        2: _agg_ips(10),  # excess 7
    }
    hard, _ = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert [f.remnawave_id for f in hard] == [2, 1]


def test_resolve_and_filter_candidates_ips_sorted_most_recent_first() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 1}}
    aggregated = {
        1: {
            "1.1.1.1": AggregatedIp(ip="1.1.1.1", node_names=("DE-1",), last_seen=_T1),
            "2.2.2.2": AggregatedIp(ip="2.2.2.2", node_names=("DE-1",), last_seen=_T2),
            "3.3.3.3": AggregatedIp(ip="3.3.3.3", node_names=("DE-1",), last_seen=_T1),
            "4.4.4.4": AggregatedIp(ip="4.4.4.4", node_names=("DE-1",), last_seen=_T1),
        }
    }
    hard, _ = _resolve_and_filter_candidates(aggregated, user_index, make_config())
    assert hard[0].ips[0].ip == "2.2.2.2"  # _T2 is more recent than _T1


def test_resolve_and_filter_candidates_user_whitelist_skips_entirely() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 1}}
    aggregated = {1: _agg_ips(10)}
    cfg = make_config(antifraud_whitelist_user_ids=[1])
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, cfg)
    assert hard == []
    assert soft == []


def test_resolve_and_filter_candidates_proportional_slack() -> None:
    # limit 10, slack 2, multiplier 0.5 -> threshold = 10 + 2 + floor(10*0.5) = 17
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 10}}
    aggregated = {1: _agg_ips(18)}
    cfg = make_config(antifraud_ip_slack_multiplier=0.5)
    hard, _ = _resolve_and_filter_candidates(aggregated, user_index, cfg)
    assert hard[0].threshold == 17
    assert hard[0].is_hard is True


def test_resolve_and_filter_candidates_soft_between_limit_and_hard_threshold() -> None:
    # limit 3, slack 2 -> hard threshold 5. group_count 4 is soft-range.
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 3}}
    aggregated = {1: _agg_ips(4)}
    cfg = make_config(antifraud_soft_alerts_enabled=True)
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, cfg)
    assert hard == []
    assert len(soft) == 1
    assert soft[0].is_hard is False
    assert soft[0].threshold == 5


def test_resolve_and_filter_candidates_soft_not_returned_when_disabled() -> None:
    user_index = {1: {"username": "u1", "telegramId": None, "hwidDeviceLimit": 3}}
    aggregated = {1: _agg_ips(4)}
    cfg = make_config(antifraud_soft_alerts_enabled=False)
    hard, soft = _resolve_and_filter_candidates(aggregated, user_index, cfg)
    assert hard == []
    assert soft == []


# ---- digest formatting ----


def test_format_digest_under_limit_shows_all() -> None:
    flagged = [
        make_flagged(remnawave_id=1, username="alice"),
        make_flagged(remnawave_id=2, username="bob"),
    ]
    text = _format_digest(flagged, hard=True)
    assert "alice" in text
    assert "bob" in text
    assert "…" not in text


def test_format_digest_respects_telegram_char_limit() -> None:
    flagged = [
        make_flagged(
            remnawave_id=i,
            username=f"user_{i}",
            ips=tuple(
                AggregatedIp(ip=f"10.0.{i}.{j}", node_names=("DE-1",), last_seen=_T1)
                for j in range(20)
            ),
        )
        for i in range(200)
    ]
    text = _format_digest(flagged, hard=True)
    assert len(text) <= TELEGRAM_MESSAGE_LIMIT
    assert "не показано" in text


def test_format_digest_caps_ip_examples_per_user() -> None:
    ips = tuple(
        AggregatedIp(ip=f"10.0.0.{i}", node_names=("DE-1",), last_seen=_T1) for i in range(50)
    )
    flagged = [make_flagged(ips=ips)]
    text = _format_digest(flagged, hard=True)
    assert "+45 ещё" in text


def test_format_digest_escapes_html() -> None:
    flagged = [make_flagged(username="<script>evil</script>")]
    text = _format_digest(flagged, hard=True)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_format_digest_shows_device_limit_and_threshold() -> None:
    flagged = [make_flagged(hwid_device_limit=3, threshold=5, ip_count=8, group_count=8)]
    text = _format_digest(flagged, hard=True)
    assert "лимит 3" in text
    assert "порог 5" in text
    assert "IP: 8" in text


def test_format_digest_shows_node_and_time() -> None:
    flagged = [
        make_flagged(ips=(AggregatedIp(ip="9.9.9.9", node_names=("DE-1", "FI-2"), last_seen=_T1),))
    ]
    text = _format_digest(flagged, hard=True)
    assert "9.9.9.9" in text
    assert "DE-1, FI-2" in text
    assert "17:36:22 UTC" in text


def test_format_digest_shows_clickable_ipinfo_link() -> None:
    flagged = [make_flagged(ips=(AggregatedIp(ip="9.9.9.9", node_names=("DE-1",), last_seen=_T1),))]
    text = _format_digest(flagged, hard=True)
    assert 'href="https://ipinfo.io/9.9.9.9"' in text


def test_format_digest_shows_asn_org_when_present() -> None:
    flagged = [
        make_flagged(
            ips=(
                AggregatedIp(
                    ip="1.1.1.1",
                    node_names=("DE-1",),
                    last_seen=_T1,
                    asn=13335,
                    asn_org="Cloudflare",
                ),
            )
        )
    ]
    text = _format_digest(flagged, hard=True)
    assert "Cloudflare" in text


def test_format_digest_hard_vs_soft_header_wording() -> None:
    flagged = [make_flagged()]
    hard_text = _format_digest(flagged, hard=True)
    soft_text = _format_digest(flagged, hard=False)
    assert "подозрением на шеринг" in hard_text
    assert "информационно" in soft_text


def test_format_digest_asn_grouping_shows_asn_count_in_header() -> None:
    flagged = [make_flagged(grouping_mode="asn", group_count=2, ip_count=8, threshold=5)]
    text = _format_digest(flagged, hard=True)
    assert "ASN: 2" in text


# ---- criteria line formatting ----


def test_format_criteria_breakdown_shows_ru_and_payment_warning() -> None:
    f = make_flagged(
        ru_node_ip_count=5, ru_node_threshold=2, no_active_payment=True, criteria_matched=3
    )

    breakdown = _format_criteria_breakdown(f)

    assert "RU-ноды: 5" in breakdown
    assert "порог 2" in breakdown
    assert "нет активной подписки" in breakdown
    assert "превышен" in breakdown


def test_format_criteria_breakdown_shows_unknown_payment() -> None:
    f = make_flagged(
        ru_node_ip_count=0, ru_node_threshold=2, no_active_payment=None, criteria_matched=1
    )

    breakdown = _format_criteria_breakdown(f)

    assert "не проверялась" in breakdown


def test_format_criteria_breakdown_marks_ru_not_exceeded_at_threshold() -> None:
    f = make_flagged(ru_node_ip_count=2, ru_node_threshold=2, no_active_payment=False)

    breakdown = _format_criteria_breakdown(f)

    assert "RU-ноды: 2 (порог 2) — не превышен" in breakdown
    assert "➖ Оплата: активна" in breakdown


# ---- digest keyboard ----


def test_make_digest_keyboard_adds_block_button_regardless_of_criteria_matched() -> None:
    f = make_flagged(telegram_id=555, criteria_matched=1)

    keyboard = _make_digest_keyboard([f])

    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "antifraud_block:1:555" in callback_datas


def test_make_digest_keyboard_omits_block_button_without_telegram_id() -> None:
    f = make_flagged(telegram_id=None, criteria_matched=3)

    keyboard = _make_digest_keyboard([f])

    assert keyboard.inline_keyboard == []


def test_mark_blocked_in_keyboard_replaces_matching_button() -> None:
    keyboard = _make_digest_keyboard(
        [
            make_flagged(remnawave_id=1, telegram_id=555),
            make_flagged(remnawave_id=2, telegram_id=777),
        ]
    )

    updated = _mark_blocked_in_keyboard(keyboard, remnawave_id=1)

    buttons = [btn for row in updated.inline_keyboard for btn in row]
    blocked_btn = next(b for b in buttons if b.callback_data == "antifraud_noop")
    assert blocked_btn.text == "✅ Заблокирован"
    other_btn = next(b for b in buttons if b.callback_data == "antifraud_block:2:777")
    assert other_btn.text == "🚫 Заблокировать"


def test_mark_blocked_in_keyboard_no_match_leaves_keyboard_unchanged() -> None:
    keyboard = _make_digest_keyboard([make_flagged(remnawave_id=1, telegram_id=555)])

    updated = _mark_blocked_in_keyboard(keyboard, remnawave_id=999)

    callback_datas = [btn.callback_data for row in updated.inline_keyboard for btn in row]
    assert callback_datas == ["antifraud_block:1:555"]


# ---- auto-block digest ----


def test_format_auto_block_digest_lists_users() -> None:
    f = make_flagged(
        username="fraudster1",
        telegram_id=555,
        ru_node_ip_count=4,
        ru_node_threshold=2,
        no_active_payment=True,
        criteria_matched=3,
    )

    digest = _format_auto_block_digest([f])

    assert "fraudster1" in digest
    assert "автоматически заблокировано" in digest
    assert "3/3" in digest
    # Regression: auto-block digest used to omit IPs entirely, leaving admins
    # unable to cross-check the block against the panel's own connection data.
    assert "1.1.1.1" in digest
    assert "2.2.2.2" in digest


# ---- RU node prefix extraction ----


def test_node_prefix_splits_on_dash() -> None:
    assert _node_prefix("RU-1") == "RU"
    assert _node_prefix("DE-Frankfurt-2") == "DE"


def test_node_prefix_returns_whole_name_without_dash() -> None:
    assert _node_prefix("standalone") == "standalone"


def test_node_prefix_handles_letters_directly_followed_by_digits() -> None:
    # Real panel node names aren't uniformly "PREFIX-rest" — "RU11" (no
    # dash) coexists with "RU-6" (dash) on the same fleet.
    assert _node_prefix("RU11") == "RU"
    assert _node_prefix("US2") == "US"


# ---- RU node group counting ----


def test_ru_node_group_count_counts_only_ru_nodes() -> None:
    ips = (
        AggregatedIp(ip="1.1.1.1", node_names=("RU-1",), last_seen=_T1),
        AggregatedIp(ip="2.2.2.2", node_names=("RU-2",), last_seen=_T1),
        AggregatedIp(ip="3.3.3.3", node_names=("DE-1",), last_seen=_T1),
    )

    count = _ru_node_group_count(ips, "ip", 24, {"RU"})

    assert count == 2


def test_ru_node_group_count_zero_when_no_ru_nodes() -> None:
    ips = (AggregatedIp(ip="3.3.3.3", node_names=("DE-1",), last_seen=_T1),)

    count = _ru_node_group_count(ips, "ip", 24, {"RU"})

    assert count == 0


def test_ru_node_group_count_counts_ip_seen_on_both_ru_and_foreign_node() -> None:
    ips = (AggregatedIp(ip="1.1.1.1", node_names=("RU-1", "DE-1"), last_seen=_T1),)

    count = _ru_node_group_count(ips, "ip", 24, {"RU"})

    assert count == 1


def test_ru_node_group_count_respects_subnet_grouping_mode() -> None:
    ips = (
        AggregatedIp(ip="1.1.1.1", node_names=("RU-1",), last_seen=_T1),
        AggregatedIp(ip="1.1.1.2", node_names=("RU-1",), last_seen=_T1),
    )

    count = _ru_node_group_count(ips, "subnet", 24, {"RU"})

    assert count == 1


def test_ru_node_group_count_counts_dashless_node_names() -> None:
    # Regression: real fleet mixes "RU11" (no dash) with "RU-6" (dash) —
    # both must count as RU nodes.
    ips = (
        AggregatedIp(ip="1.1.1.1", node_names=("RU11",), last_seen=_T1),
        AggregatedIp(ip="2.2.2.2", node_names=("RU11",), last_seen=_T1),
        AggregatedIp(ip="3.3.3.3", node_names=("RU-6",), last_seen=_T1),
        AggregatedIp(ip="4.4.4.4", node_names=("US-2",), last_seen=_T1),
    )

    count = _ru_node_group_count(ips, "ip", 24, {"RU"})

    assert count == 3


# ---- drop connections ----


async def test_drop_connections_true_on_success() -> None:
    raw_client = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    raw_client.post = AsyncMock(return_value=response)

    result = await _drop_connections(raw_client, 42)

    assert result is True
    raw_client.post.assert_awaited_once_with(
        "/connections/drop",
        json={"dropBy": {"by": "userIds", "userIds": [42]}, "targetNodes": {"target": "allNodes"}},
    )


async def test_drop_connections_false_on_http_error() -> None:
    raw_client = MagicMock()
    raw_client.post = AsyncMock(side_effect=Exception("boom"))

    result = await _drop_connections(raw_client, 42)

    assert result is False


# ---- payment status resolution + hard candidate enrichment ----


async def test_resolve_payment_bounded_maps_by_telegram_id() -> None:
    client = MagicMock()

    async def fake_check(client_arg, telegram_id):
        return telegram_id == 111

    import src.apps.antifraud.controllers.scheduler.tasks as tasks_mod

    original = tasks_mod.check_no_active_payment
    tasks_mod.check_no_active_payment = fake_check
    try:
        result = await _resolve_payment_bounded(client, [111, 222], concurrency=8)
    finally:
        tasks_mod.check_no_active_payment = original

    assert result == {111: True, 222: False}


async def test_enrich_hard_computes_ru_and_payment_and_criteria_matched() -> None:
    config = make_config(antifraud_ru_node_prefixes=["RU"], antifraud_ru_node_ip_threshold=1)
    flagged = make_flagged(
        remnawave_id=1,
        telegram_id=111,
        ips=(
            AggregatedIp(ip="1.1.1.1", node_names=("RU-1",), last_seen=_T1),
            AggregatedIp(ip="2.2.2.2", node_names=("RU-2",), last_seen=_T1),
        ),
    )

    import src.apps.antifraud.controllers.scheduler.tasks as tasks_mod

    original = tasks_mod.check_no_active_payment
    tasks_mod.check_no_active_payment = AsyncMock(return_value=True)
    try:
        result = await _enrich_hard_with_new_criteria([flagged], config, MagicMock())
    finally:
        tasks_mod.check_no_active_payment = original

    assert len(result) == 1
    enriched = result[0]
    assert enriched.ru_node_ip_count == 2
    assert enriched.ru_node_threshold == 1
    assert enriched.no_active_payment is True
    assert enriched.criteria_matched == 3  # is_hard + ru + payment


async def test_enrich_hard_skips_payment_check_without_telegram_id() -> None:
    config = make_config(antifraud_ru_node_prefixes=["RU"], antifraud_ru_node_ip_threshold=99)
    flagged = make_flagged(remnawave_id=1, telegram_id=None)

    result = await _enrich_hard_with_new_criteria([flagged], config, MagicMock())

    assert result[0].no_active_payment is None
    assert result[0].criteria_matched == 1  # только is_hard, ru ниже порога, оплата не проверялась


async def test_enrich_hard_criteria_matched_excludes_unknown_payment() -> None:
    config = make_config(antifraud_ru_node_prefixes=["RU"], antifraud_ru_node_ip_threshold=99)
    flagged = make_flagged(remnawave_id=1, telegram_id=111)

    import src.apps.antifraud.controllers.scheduler.tasks as tasks_mod

    original = tasks_mod.check_no_active_payment
    tasks_mod.check_no_active_payment = AsyncMock(return_value=None)
    try:
        result = await _enrich_hard_with_new_criteria([flagged], config, MagicMock())
    finally:
        tasks_mod.check_no_active_payment = original

    assert result[0].no_active_payment is None
    assert result[0].criteria_matched == 1  # неизвестный статус оплаты не засчитывается

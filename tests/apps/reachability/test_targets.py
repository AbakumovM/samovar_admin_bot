from typing import Any

from src.apps.reachability.domain.targets import IpTarget, build_targets, select_hosts


def _host(remark: str, address: str, tags: list[str] | None, **kw: Any) -> dict[str, Any]:
    host: dict[str, Any] = {
        "remark": remark,
        "address": address,
        "port": 443,
        "sni": None,
        "tags": tags,
        "isDisabled": False,
        "nodes": [],
    }
    host.update(kw)
    return host


def test_select_hosts_filters_by_tags_and_disabled() -> None:
    hosts = [
        _host("cdn", "a.com", ["CDN"]),
        _host("none", "b.com", None),
        _host("off", "c.com", ["SELF"], isDisabled=True),
        _host("gem", "d.com", ["SELF", "GEMINI"]),
    ]
    selected = select_hosts(hosts, {"SELF", "GEMINI"})
    assert [h["remark"] for h in selected] == ["gem"]


def test_same_ip_two_tiles_one_target() -> None:
    hosts = [
        _host("🇳🇱 Нидерланды", "nl3.samovargate.com", ["SELF"], nodes=["u1"]),
        _host("SMART · NL-3", "nl3.samovargate.com", ["SMART_MAIN"], nodes=["u1"]),
    ]
    nodes = [{"uuid": "u1", "name": "NL-3"}]
    targets = build_targets(hosts, nodes, {"nl3.samovargate.com": ["2.27.201.110"]})
    assert targets == [
        IpTarget(
            ip="2.27.201.110",
            port=443,
            sni="nl3.samovargate.com",
            tiles=(
                "🇳🇱 Нидерланды (nl3.samovargate.com)",
                "SMART · NL-3 (nl3.samovargate.com)",
            ),
            node_names=("NL-3",),
            hosters=(),
        )
    ]


def test_ip_literal_has_no_sni() -> None:
    targets = build_targets(
        [_host("x", "188.72.111.36", ["SELF"])], [], {"188.72.111.36": ["188.72.111.36"]}
    )
    assert targets[0].sni is None


def test_explicit_sni_wins() -> None:
    targets = build_targets(
        [_host("x", "a.com", ["SELF"], sni="x.com")], [], {"a.com": ["1.2.3.4"]}
    )
    assert targets[0].sni == "x.com"


def test_unresolved_address_skipped() -> None:
    assert build_targets([_host("x", "a.com", ["SELF"])], [], {}) == []


def test_hosters_from_node_provider() -> None:
    hosts = [
        _host("a", "x.com", ["SELF"], nodes=["u1", "u2", "u3"]),
    ]
    nodes = [
        {
            "uuid": "u1",
            "name": "N1",
            "provider": {"name": "play2go", "loginUrl": "https://play2go.cloud/me"},
        },
        {
            "uuid": "u2",
            "name": "N2",
            "provider": {"name": "play2go", "loginUrl": "https://play2go.cloud/me"},
        },
        {"uuid": "u3", "name": "N3", "provider": {"name": "4vps.su", "loginUrl": None}},
    ]
    target = build_targets(hosts, nodes, {"x.com": ["1.2.3.4"]})[0]
    assert target.hosters == (("4vps.su", None), ("play2go", "https://play2go.cloud/me"))


def test_no_provider_no_hosters() -> None:
    nodes = [{"uuid": "u1", "name": "N1", "provider": None}]
    target = build_targets(
        [_host("a", "x.com", ["SELF"], nodes=["u1"])], nodes, {"x.com": ["1.2.3.4"]}
    )[0]
    assert target.hosters == ()

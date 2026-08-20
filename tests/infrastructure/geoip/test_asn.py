from unittest.mock import MagicMock, patch

from src.infrastructure.geoip.asn import AsnInfo, MaxMindAsnResolver, NopAsnResolver


def test_nop_resolver_always_returns_none() -> None:
    resolver = NopAsnResolver()
    assert resolver.lookup("1.2.3.4") is None


def test_maxmind_resolver_missing_database_lookup_returns_none() -> None:
    resolver = MaxMindAsnResolver("/nonexistent/path/GeoLite2-ASN.mmdb")
    assert resolver.lookup("1.2.3.4") is None


def test_maxmind_resolver_reload_missing_database_does_not_raise() -> None:
    resolver = MaxMindAsnResolver("/nonexistent/path/GeoLite2-ASN.mmdb")
    resolver.reload()  # should log a warning, not raise
    assert resolver.lookup("1.2.3.4") is None


def _make_reader(get_return: object) -> MagicMock:
    reader = MagicMock()
    reader.get = MagicMock(return_value=get_return)
    return reader


def test_maxmind_resolver_lookup_returns_asn_info() -> None:
    reader = _make_reader(
        {"autonomous_system_number": 13335, "autonomous_system_organization": "Cloudflare"}
    )
    with patch("src.infrastructure.geoip.asn.maxminddb.open_database", return_value=reader):
        resolver = MaxMindAsnResolver("/fake/path.mmdb")
    assert resolver.lookup("1.1.1.1") == AsnInfo(number=13335, org="Cloudflare")


def test_maxmind_resolver_lookup_missing_asn_number_returns_none() -> None:
    reader = _make_reader({"autonomous_system_organization": "Cloudflare"})
    with patch("src.infrastructure.geoip.asn.maxminddb.open_database", return_value=reader):
        resolver = MaxMindAsnResolver("/fake/path.mmdb")
    assert resolver.lookup("1.1.1.1") is None


def test_maxmind_resolver_lookup_no_match_returns_none() -> None:
    reader = _make_reader(None)
    with patch("src.infrastructure.geoip.asn.maxminddb.open_database", return_value=reader):
        resolver = MaxMindAsnResolver("/fake/path.mmdb")
    assert resolver.lookup("1.1.1.1") is None


def test_maxmind_resolver_lookup_invalid_ip_returns_none() -> None:
    reader = _make_reader({})
    reader.get.side_effect = ValueError("invalid ip")
    with patch("src.infrastructure.geoip.asn.maxminddb.open_database", return_value=reader):
        resolver = MaxMindAsnResolver("/fake/path.mmdb")
    assert resolver.lookup("not-an-ip") is None


def test_maxmind_resolver_reload_closes_old_reader() -> None:
    old_reader = _make_reader({})
    new_reader = _make_reader({})
    with patch("src.infrastructure.geoip.asn.maxminddb.open_database", return_value=old_reader):
        resolver = MaxMindAsnResolver("/fake/path.mmdb")
    with patch("src.infrastructure.geoip.asn.maxminddb.open_database", return_value=new_reader):
        resolver.reload()
    old_reader.close.assert_called_once()

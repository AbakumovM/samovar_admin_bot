from datetime import UTC, datetime

from src.apps.reachability.domain.formatting import (
    IpChange,
    ReminderItem,
    format_digest,
    format_point_down,
    format_point_up,
    format_reminder,
    reason_control,
    reason_ssh,
)
from src.apps.reachability.domain.targets import IpTarget

BLOCKED = IpChange(
    IpTarget(
        "157.22.177.33",
        443,
        "nl1.samovargate.com",
        ("🇳🇱 Нидерланды (nl1.samovargate.com)",),
        ("NL-1",),
        (("4vps.su", "https://4vps.su"),),
    ),
    "ok",
    "blocked",
    {"RU-10": "timeout", "TW2": "timeout", "снаружи": "ok"},
)
RECOVERED = IpChange(
    IpTarget(
        "147.45.179.34",
        443,
        "hazel.nodlsd.com",
        ("🇬🇧 Великобритания (hazel.nodlsd.com)",),
        ("UK-1",),
    ),
    "blocked",
    "ok",
    {"RU-10": "ok", "TW2": "ok", "снаружи": "ok"},
)


def test_digest_exact_text_and_order() -> None:
    assert format_digest([RECOVERED, BLOCKED], ["RU-10", "TW2"]) == [
        "🛰 Проверка блокировок: изменения\n\n"
        "🚫 Заблокирован: 157.22.177.33\n"
        "Плитки: 🇳🇱 Нидерланды (nl1.samovargate.com)\n"
        "Ноды: NL-1\n"
        "RU-10 ❌ · TW2 ❌ · снаружи ✅\n"
        'Хостер: <a href="https://4vps.su">4vps.su</a>\n\n'
        "✅ Снова доступен: 147.45.179.34\n"
        "Плитки: 🇬🇧 Великобритания (hazel.nodlsd.com)\n"
        "Ноды: UK-1"
    ]


def test_partial_with_paused_point() -> None:
    change = IpChange(
        IpTarget("2.27.201.110", 443, None, ("t (a)",), ("NL-3",)),
        "ok",
        "partial",
        {"RU-10": "timeout", "TW2": None, "снаружи": "ok"},
    )
    text = format_digest([change], ["RU-10", "TW2"])[0]
    assert "⚠️ Частичная блокировка: 2.27.201.110" in text
    assert "RU-10 ❌ · TW2 ⏸ · снаружи ✅" in text


def test_tiles_truncated_and_escaped() -> None:
    tiles = ("<a>", "b", "c", "d", "e", "f", "g")
    change = IpChange(IpTarget("1.1.1.1", 443, None, tiles, ()), "ok", "blocked", {"снаружи": "ok"})
    text = format_digest([change], [])[0]
    assert "Плитки: &lt;a&gt;, b, c, d, e +2" in text


def test_digest_split_under_limit() -> None:
    changes = [
        IpChange(
            IpTarget(f"10.0.0.{i}", 443, None, ("x" * 60,), ("N",)),
            "ok",
            "blocked",
            {"RU-10": "timeout", "снаружи": "ok"},
        )
        for i in range(60)
    ]
    messages = format_digest(changes, ["RU-10"])
    assert len(messages) > 1
    assert all(len(m) <= 4000 for m in messages)
    assert all(m.startswith("🛰 Проверка блокировок: изменения\n\n") for m in messages)
    assert sum(m.count("🚫 Заблокирован:") for m in messages) == 60


def test_point_messages() -> None:
    assert format_point_down("RU-10", reason_ssh(), 1, False) == (
        "⚠️ Точка проверки RU-10 не работает: не отвечает по SSH\n"
        "Проверка блокировок идёт по оставшимся точкам."
    )
    assert format_point_down("RU-10", reason_control(1, 4), 0, False) == (
        "⚠️ Точка проверки RU-10 не работает: не видит контрольные адреса (открыто 1 из 4)\n"
        "Проверка блокировок приостановлена: нет работающих точек в РФ."
    )
    assert format_point_down("снаружи", reason_ssh(), 2, True).endswith(
        "\nПроверка блокировок приостановлена."
    )
    assert format_point_up("RU-10") == "✅ Точка проверки RU-10 снова работает"


def test_nodes_line_omitted_when_unknown() -> None:
    change = IpChange(
        IpTarget("2.26.101.143", 443, None, ("EXITSW (sw1.samovargate.com)",), ()),
        "ok",
        "blocked",
        {"RU-10": "timeout", "снаружи": "ok"},
    )
    text = format_digest([change], ["RU-10"])[0]
    assert "Ноды:" not in text
    assert "Плитки: EXITSW (sw1.samovargate.com)\nRU-10 ❌ · снаружи ✅" in text


def test_reminder_exact_text() -> None:
    uk = IpTarget(
        "147.45.179.34",
        443,
        "hazel.nodlsd.com",
        ("🇬🇧 Великобритания (hazel.nodlsd.com)",),
        ("UK-1",),
        (("4vps.su", "https://4vps.su"),),
    )
    nl = IpTarget(
        "2.27.201.110",
        443,
        None,
        ("🇳🇱 Нидерланды (nl3.samovargate.com)",),
        ("NL-3",),
        (("play2go", "https://play2go.cloud/me"), ("x&y", None)),
    )
    items = [
        ReminderItem(nl, "partial", datetime(2026, 11, 16, 9, 10, tzinfo=UTC)),
        ReminderItem(uk, "blocked", datetime(2026, 11, 16, 15, 44, tzinfo=UTC)),
    ]
    assert format_reminder(items) == [
        "🔁 Всё ещё заблокированы\n\n"
        "🚫 147.45.179.34 — с 16.11 18:44 МСК\n"
        "Плитки: 🇬🇧 Великобритания (hazel.nodlsd.com)\n"
        "Ноды: UK-1\n"
        'Хостер: <a href="https://4vps.su">4vps.su</a>\n\n'
        "⚠️ 2.27.201.110 (частично) — с 16.11 12:10 МСК\n"
        "Плитки: 🇳🇱 Нидерланды (nl3.samovargate.com)\n"
        "Ноды: NL-3\n"
        'Хостер: <a href="https://play2go.cloud/me">play2go</a>, x&amp;y'
    ]


def test_reminder_without_since_and_hosters() -> None:
    target = IpTarget("1.1.1.1", 443, None, ("t (a)",), (), ())
    text = format_reminder([ReminderItem(target, "blocked", None)])[0]
    assert text == "🔁 Всё ещё заблокированы\n\n🚫 1.1.1.1\nПлитки: t (a)"

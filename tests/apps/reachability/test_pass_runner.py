from datetime import UTC, datetime, timedelta
from typing import Any

from src.apps.reachability.controllers.scheduler.pass_runner import (
    PassResult,
    PointTracker,
    run_pass,
)
from src.apps.reachability.domain.models import IpState
from src.infrastructure.reachability.ssh_runner import ProbePoint

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
IP = "1.2.3.4"
POINTS = [ProbePoint("RU-10", "10.0.0.1"), ProbePoint("TW2", "10.0.0.2")]
CONTROL = [{"ip": f"9.9.9.{i}", "port": 443, "sni": f"c{i}.com"} for i in range(4)]
HOSTS = [
    {
        "remark": "🇳🇱 Нидерланды",
        "address": "nl1.samovargate.com",
        "port": 443,
        "sni": None,
        "tags": ["SELF"],
        "isDisabled": False,
        "nodes": ["u1"],
    }
]
NODES = [{"uuid": "u1", "name": "NL-1"}]
RESOLVED = {"nl1.samovargate.com": [IP]}


class MemoryStore:
    def __init__(self, initial: dict[str, IpState] | None = None) -> None:
        self.states: dict[str, IpState] = dict(initial or {})
        self.saves = 0

    async def get(self, ips: list[str]) -> dict[str, IpState]:
        return {ip: self.states[ip] for ip in ips if ip in self.states}

    async def save(
        self,
        state: IpState,
        last_results: dict[str, str | None],
        checked_at: datetime,
        changed: bool,
    ) -> None:
        self.states[state.ip] = state
        self.saves += 1


def _answer(payload: list[dict[str, Any]], target: str, control: str) -> list[dict[str, Any]]:
    return [
        {**t, "result": control if t["ip"].startswith("9.9.9.") else target, "ms": 1}
        for t in payload
    ]


def _point_runner(behaviour: dict[str, tuple[str, str] | None]) -> Any:
    async def run_point(
        point: ProbePoint, payload: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        spec = behaviour[point.name]
        return None if spec is None else _answer(payload, *spec)

    return run_point


def _outside(target: str = "ok", control: str = "ok") -> Any:
    async def run_outside(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _answer(payload, target, control)

    return run_outside


async def _pass(
    store: MemoryStore,
    tracker: PointTracker,
    behaviour: dict[str, tuple[str, str] | None],
    outside: Any = None,
) -> PassResult:
    return await run_pass(
        hosts=HOSTS,
        nodes=NODES,
        resolved=RESOLVED,
        control_targets=CONTROL,
        tags={"SELF"},
        points=POINTS,
        run_point=_point_runner(behaviour),
        run_outside=outside or _outside(),
        states=store,
        tracker=tracker,
        confirm_passes=2,
        min_ok_ratio=0.5,
        reminder_after=timedelta(hours=6),
        now=NOW,
    )


BLOCKED = {"RU-10": ("timeout", "ok"), "TW2": ("timeout", "ok")}
ALL_OK = {"RU-10": ("ok", "ok"), "TW2": ("ok", "ok")}


async def test_block_confirmed_after_two_passes() -> None:
    store, tracker = MemoryStore({IP: IpState(IP, "ok", None, 0)}), PointTracker()
    first = await _pass(store, tracker, BLOCKED)
    assert first.messages == []
    second = await _pass(store, tracker, BLOCKED)
    assert len(second.messages) == 1
    assert "🚫 Заблокирован: 1.2.3.4" in second.messages[0]
    assert "RU-10 ❌ · TW2 ❌ · снаружи ✅" in second.messages[0]
    assert store.states[IP].status == "blocked"
    assert second.not_ok == 1
    assert second.checked == 1


async def test_first_ok_is_silent() -> None:
    store, tracker = MemoryStore(), PointTracker()
    await _pass(store, tracker, ALL_OK)
    result = await _pass(store, tracker, ALL_OK)
    assert result.messages == []
    assert store.states[IP].status == "ok"


async def test_outside_down_skips_ip() -> None:
    store = MemoryStore({IP: IpState(IP, "ok", "blocked", 1)})
    await _pass(store, PointTracker(), BLOCKED, outside=_outside(target="timeout"))
    assert store.saves == 0
    assert store.states[IP] == IpState(IP, "ok", "blocked", 1)


async def test_point_unhealthy_ignored() -> None:
    store, tracker = MemoryStore({IP: IpState(IP, "ok", None, 0)}), PointTracker()
    behaviour = {"RU-10": ("timeout", "ok"), "TW2": ("timeout", "timeout")}
    await _pass(store, tracker, behaviour)
    second = await _pass(store, tracker, behaviour)
    assert store.states[IP].status == "blocked"
    text = "\n".join(second.messages)
    assert "TW2 ⏸" in text
    assert "⚠️ Точка проверки TW2 не работает: не видит контрольные адреса (открыто 0 из 4)" in text


async def test_ssh_failure_reason() -> None:
    store, tracker = MemoryStore(), PointTracker()
    behaviour: dict[str, tuple[str, str] | None] = {"RU-10": None, "TW2": ("ok", "ok")}
    await _pass(store, tracker, behaviour)
    second = await _pass(store, tracker, behaviour)
    assert any("Точка проверки RU-10 не работает: не отвечает по SSH" in m for m in second.messages)


async def test_no_healthy_ru_points_skips_pass() -> None:
    store = MemoryStore()
    result = await _pass(store, PointTracker(), {"RU-10": None, "TW2": None})
    assert result.skipped is True
    assert store.saves == 0


async def test_outside_unhealthy_skips_pass() -> None:
    store = MemoryStore()
    result = await _pass(store, PointTracker(), ALL_OK, outside=_outside(control="timeout"))
    assert result.skipped is True
    assert store.saves == 0


async def test_ip_returns_with_saved_status() -> None:
    store, tracker = MemoryStore({IP: IpState(IP, "blocked", None, 0, None, NOW)}), PointTracker()
    for _ in range(2):
        result = await _pass(store, tracker, BLOCKED)
        assert result.messages == []


async def test_point_recovers_message() -> None:
    store, tracker = MemoryStore(), PointTracker()
    down: dict[str, tuple[str, str] | None] = {"RU-10": None, "TW2": ("ok", "ok")}
    await _pass(store, tracker, down)
    await _pass(store, tracker, down)
    result = await _pass(store, tracker, ALL_OK)
    assert "✅ Точка проверки RU-10 снова работает" in result.messages


async def test_confirmed_change_stamps_changed_and_notified() -> None:
    store, tracker = MemoryStore({IP: IpState(IP, "ok", None, 0)}), PointTracker()
    await _pass(store, tracker, BLOCKED)
    await _pass(store, tracker, BLOCKED)
    assert store.states[IP].changed_at == NOW
    assert store.states[IP].notified_at == NOW


async def test_reminder_after_six_hours() -> None:
    since = NOW - timedelta(hours=10)
    store = MemoryStore({IP: IpState(IP, "blocked", None, 0, since, NOW - timedelta(hours=7))})
    result = await _pass(store, PointTracker(), BLOCKED)
    assert len(result.messages) == 1
    assert result.messages[0].startswith(
        "🔁 Всё ещё заблокированы\n\n🚫 1.2.3.4 — с 16.11 05:00 МСК"
    )
    assert store.states[IP].notified_at == NOW
    assert store.states[IP].changed_at == since


async def test_no_reminder_within_six_hours() -> None:
    store = MemoryStore({IP: IpState(IP, "blocked", None, 0, None, NOW - timedelta(hours=1))})
    result = await _pass(store, PointTracker(), BLOCKED)
    assert result.messages == []


async def test_legacy_blocked_without_notified_at_is_reminded() -> None:
    store = MemoryStore({IP: IpState(IP, "blocked", None, 0)})
    result = await _pass(store, PointTracker(), BLOCKED)
    assert any(m.startswith("🔁 Всё ещё заблокированы") for m in result.messages)


async def test_ok_ip_never_reminded() -> None:
    store = MemoryStore({IP: IpState(IP, "ok", None, 0, None, NOW - timedelta(days=2))})
    result = await _pass(store, PointTracker(), ALL_OK)
    assert result.messages == []

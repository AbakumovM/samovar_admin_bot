import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from src.apps.reachability.domain.formatting import (
    OUTSIDE,
    IpChange,
    format_digest,
    format_point_down,
    format_point_up,
    reason_control,
    reason_ssh,
)
from src.apps.reachability.domain.logic import advance, is_point_healthy, observe, should_notify
from src.apps.reachability.domain.models import IpState
from src.apps.reachability.domain.targets import build_targets, select_hosts
from src.infrastructure.reachability.ssh_runner import ProbePoint

Results = list[dict[str, Any]]
RunPoint = Callable[[ProbePoint, Results], Awaitable[Results | None]]
RunOutside = Callable[[Results], Awaitable[Results]]


class StateStore(Protocol):
    async def get(self, ips: list[str]) -> dict[str, IpState]: ...

    async def save(
        self,
        state: IpState,
        last_results: dict[str, str | None],
        checked_at: datetime,
        changed: bool,
    ) -> None: ...


@dataclass
class _PointHealth:
    unhealthy_streak: int = 0
    alerted: bool = False


PASS_KEY = "__pass__"  # tracks consecutive failures of the whole pass


@dataclass
class PointTracker:
    """In-memory health history of probe points (resets on restart).

    `lock` serializes passes: the scheduled loop and /blocks_check share this
    singleton, and two concurrent passes would double-confirm statuses.
    """

    _points: dict[str, _PointHealth] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def down_points(self) -> list[str]:
        return [name for name, h in self._points.items() if h.alerted and name != PASS_KEY]

    def observe(
        self, name: str, healthy: bool, confirm_passes: int
    ) -> Literal["down", "up"] | None:
        health = self._points.setdefault(name, _PointHealth())
        if healthy:
            health.unhealthy_streak = 0
            if health.alerted:
                health.alerted = False
                return "up"
            return None
        health.unhealthy_streak += 1
        if health.unhealthy_streak >= confirm_passes and not health.alerted:
            health.alerted = True
            return "down"
        return None


@dataclass(frozen=True)
class PassResult:
    checked: int
    not_ok: int
    skipped: bool
    messages: list[str]


def _health(
    results: Results | None, control_count: int, min_ok_ratio: float
) -> tuple[bool, str | None]:
    """(healthy, reason if not) judged by the control targets at the end of `results`."""
    if results is None:
        return False, reason_ssh()
    control = [r["result"] for r in results[len(results) - control_count :]]
    if is_point_healthy(control, min_ok_ratio):
        return True, None
    return False, reason_control(control.count("ok"), len(control))


def _count_not_ok(states: dict[str, IpState]) -> int:
    return sum(1 for state in states.values() if state.status in ("partial", "blocked"))


async def run_pass(
    *,
    hosts: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    resolved: dict[str, list[str]],
    control_targets: Results,
    tags: set[str],
    points: list[ProbePoint],
    run_point: RunPoint,
    run_outside: RunOutside,
    states: StateStore,
    tracker: PointTracker,
    confirm_passes: int,
    min_ok_ratio: float,
    now: datetime,
) -> PassResult:
    targets = build_targets(select_hosts(hosts, tags), nodes, resolved)
    payload = [{"ip": t.ip, "port": t.port, "sni": t.sni} for t in targets] + control_targets
    control_count = len(control_targets)

    outside_results, point_results = await asyncio.gather(
        run_outside(payload), asyncio.gather(*(run_point(p, payload) for p in points))
    )

    outside_healthy, outside_reason = _health(outside_results, control_count, min_ok_ratio)
    healthy_points: dict[str, Results] = {}
    point_health: dict[str, tuple[bool, str | None]] = {}
    for point, results in zip(points, point_results, strict=True):
        healthy, reason = _health(results, control_count, min_ok_ratio)
        point_health[point.name] = (healthy, reason)
        if healthy and results is not None:
            healthy_points[point.name] = results

    messages: list[str] = []
    remaining_ru = len(healthy_points)
    for name, (healthy, reason) in [
        (OUTSIDE, (outside_healthy, outside_reason)),
        *point_health.items(),
    ]:
        event = tracker.observe(name, healthy, confirm_passes)
        if event == "down":
            messages.append(
                format_point_down(name, reason or "", remaining_ru, is_outside=name == OUTSIDE)
            )
        elif event == "up":
            messages.append(format_point_up(name))

    current = await states.get([t.ip for t in targets])

    if not outside_healthy or not healthy_points:
        return PassResult(checked=0, not_ok=_count_not_ok(current), skipped=True, messages=messages)

    changes: list[IpChange] = []
    for index, target in enumerate(targets):
        outside = str(outside_results[index]["result"])
        ru = {name: str(results[index]["result"]) for name, results in healthy_points.items()}
        observation = observe(outside, ru)
        if observation is None:
            continue
        last_results: dict[str, str | None] = {p.name: ru.get(p.name) for p in points}
        last_results[OUTSIDE] = outside
        state, transition = advance(current.get(target.ip), target.ip, observation, confirm_passes)
        current[target.ip] = state
        await states.save(state, last_results, now, changed=transition is not None)
        if transition is not None and should_notify(transition):
            changes.append(IpChange(target, transition.previous, transition.current, last_results))

    messages.extend(format_digest(changes, [p.name for p in points]))
    return PassResult(
        checked=len(targets), not_ok=_count_not_ok(current), skipped=False, messages=messages
    )

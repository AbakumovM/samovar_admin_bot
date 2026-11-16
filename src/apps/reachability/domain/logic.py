from typing import Literal

from src.apps.reachability.domain.models import IpState, Transition

Status = Literal["ok", "partial", "blocked"]


def observe(outside: str, ru: dict[str, str]) -> Status | None:
    """Classify one pass for one IP. `ru` holds only healthy RU points.

    None means "no verdict this pass": the server is down from outside too
    (not a block) or no RU point produced a usable result.
    """
    if outside != "ok" or not ru:
        return None
    ok_count = sum(1 for result in ru.values() if result == "ok")
    if ok_count == len(ru):
        return "ok"
    if ok_count == 0:
        return "blocked"
    return "partial"


def advance(
    state: IpState | None, ip: str, observation: Status, confirm_passes: int
) -> tuple[IpState, Transition | None]:
    """Accept a new status only after `confirm_passes` identical observations in a row."""
    current = state or IpState(ip=ip, status=None, pending_status=None, pending_count=0)
    if observation == current.status:
        return IpState(ip, current.status, None, 0), None

    count = current.pending_count + 1 if observation == current.pending_status else 1
    if count >= confirm_passes:
        return IpState(ip, observation, None, 0), Transition(ip, current.status, observation)
    return IpState(ip, current.status, observation, count), None


def should_notify(transition: Transition) -> bool:
    # A freshly tracked IP that turns out fine is not news.
    return not (transition.previous is None and transition.current == "ok")


def is_point_healthy(control_results: list[str], min_ok_ratio: float) -> bool:
    if not control_results:
        return False
    ok_count = sum(1 for result in control_results if result == "ok")
    return ok_count / len(control_results) >= min_ok_ratio

from src.apps.reachability.domain.logic import (
    advance,
    is_point_healthy,
    observe,
    should_notify,
)
from src.apps.reachability.domain.models import IpState, Transition

IP = "1.1.1.1"


def test_observe_outside_down_is_none() -> None:
    assert observe("timeout", {"RU-10": "ok"}) is None


def test_observe_no_points_is_none() -> None:
    assert observe("ok", {}) is None


def test_observe_all_ok() -> None:
    assert observe("ok", {"RU-10": "ok", "TW2": "ok"}) == "ok"


def test_observe_all_failed_is_blocked() -> None:
    assert observe("ok", {"RU-10": "timeout", "TW2": "tls_fail"}) == "blocked"


def test_observe_some_failed_is_partial() -> None:
    assert observe("ok", {"RU-10": "timeout", "TW2": "ok"}) == "partial"


def test_observe_single_point_blocked() -> None:
    assert observe("ok", {"TW2": "timeout"}) == "blocked"


def test_advance_new_ip_needs_confirmation() -> None:
    state, transition = advance(None, IP, "ok", 2)
    assert state.status is None
    assert transition is None

    state, transition = advance(state, IP, "ok", 2)
    assert state.status == "ok"
    assert transition == Transition(IP, None, "ok")


def test_advance_interrupted_pending_resets() -> None:
    state = IpState(IP, "ok", None, 0)
    state, transition = advance(state, IP, "blocked", 2)
    assert transition is None
    state, transition = advance(state, IP, "ok", 2)
    assert transition is None
    assert state.pending_status is None
    assert state.pending_count == 0

    state, _ = advance(state, IP, "blocked", 2)
    state, transition = advance(state, IP, "blocked", 2)
    assert transition == Transition(IP, "ok", "blocked")
    assert state.status == "blocked"


def test_advance_blocked_to_partial() -> None:
    state = IpState(IP, "blocked", None, 0)
    state, _ = advance(state, IP, "partial", 2)
    state, transition = advance(state, IP, "partial", 2)
    assert transition == Transition(IP, "blocked", "partial")


def test_should_notify() -> None:
    assert should_notify(Transition(IP, None, "ok")) is False
    assert should_notify(Transition(IP, None, "blocked")) is True
    assert should_notify(Transition(IP, "blocked", "ok")) is True


def test_is_point_healthy() -> None:
    assert is_point_healthy(["ok", "ok", "timeout", "timeout"], 0.5) is True
    assert is_point_healthy(["ok", "timeout", "timeout", "timeout"], 0.5) is False
    assert is_point_healthy([], 0.5) is False


def test_mass_block_keeps_points_healthy() -> None:
    assert is_point_healthy(["ok"] * 4, 0.5) is True
    observations = [observe("ok", {"RU-10": "timeout", "TW2": "timeout"}) for _ in range(20)]
    assert observations == ["blocked"] * 20

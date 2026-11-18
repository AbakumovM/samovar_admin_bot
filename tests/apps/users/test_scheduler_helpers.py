from src.apps.users.controllers.scheduler.alerts import ThresholdAlert
from src.apps.users.controllers.scheduler.tasks import (
    _compute_delta,
    _order_and_limit,
)

GB = 1024**3


def test_compute_delta_positive() -> None:
    assert _compute_delta(current=1000, previous=600) == 400


def test_compute_delta_zero() -> None:
    assert _compute_delta(current=1000, previous=1000) == 0


def test_compute_delta_negative_reset() -> None:
    # Counter was reset — return None to signal skip
    assert _compute_delta(current=500, previous=1000) is None


def _alert(uuid: str, gb: int, threshold: int) -> ThresholdAlert:
    return ThresholdAlert(
        user_uuid=uuid, username=uuid, telegram_id=1, total_bytes=gb * GB, threshold_gb=threshold
    )


def test_order_and_limit_critical_first_and_regular_capped() -> None:
    regular = [_alert(f"r{i}", 31 + i, 30) for i in range(12)]
    critical = [_alert("c1", 160, 150), _alert("c2", 200, 150)]

    result = _order_and_limit(regular + critical, critical_threshold_gb=150, limit=10)

    assert [a.user_uuid for a in result[:2]] == ["c2", "c1"]
    assert [a.user_uuid for a in result[2:]] == [f"r{i}" for i in range(11, 1, -1)]


def test_order_and_limit_keeps_all_critical_over_limit() -> None:
    critical = [_alert(f"c{i}", 151 + i, 150) for i in range(11)]

    result = _order_and_limit(critical, critical_threshold_gb=150, limit=10)

    assert len(result) == 11

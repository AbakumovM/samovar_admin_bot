import pytest
from src.apps.users.controllers.scheduler.tasks import _compute_delta, _is_anomaly


def test_compute_delta_positive() -> None:
    assert _compute_delta(current=1000, previous=600) == 400


def test_compute_delta_zero() -> None:
    assert _compute_delta(current=1000, previous=1000) == 0


def test_compute_delta_negative_reset() -> None:
    # Counter was reset — return None to signal skip
    assert _compute_delta(current=500, previous=1000) is None


def test_is_anomaly_both_conditions_true() -> None:
    # 60 GB today, threshold=50 GB, avg=10 GB/day, multiplier=3.0 → 60 > 50 AND 60 > 30
    assert _is_anomaly(
        bytes_today=60 * 1024**3,
        avg_daily_bytes=10 * 1024**3,
        threshold_bytes=50 * 1024**3,
        multiplier=3.0,
    ) is True


def test_is_anomaly_below_threshold() -> None:
    # 30 GB today (below 50 GB threshold) even though 3× average
    assert _is_anomaly(
        bytes_today=30 * 1024**3,
        avg_daily_bytes=5 * 1024**3,
        threshold_bytes=50 * 1024**3,
        multiplier=3.0,
    ) is False


def test_is_anomaly_below_multiplier() -> None:
    # 60 GB today, avg=30 GB/day → only 2× average, below 3× threshold
    assert _is_anomaly(
        bytes_today=60 * 1024**3,
        avg_daily_bytes=30 * 1024**3,
        threshold_bytes=50 * 1024**3,
        multiplier=3.0,
    ) is False


def test_is_anomaly_zero_average() -> None:
    # No history — never flag as anomaly
    assert _is_anomaly(
        bytes_today=100 * 1024**3,
        avg_daily_bytes=0,
        threshold_bytes=50 * 1024**3,
        multiplier=3.0,
    ) is False

from src.apps.users.controllers.scheduler.tasks import _compute_delta, _check_anomaly


def test_compute_delta_positive() -> None:
    assert _compute_delta(current=1000, previous=600) == 400


def test_compute_delta_zero() -> None:
    assert _compute_delta(current=1000, previous=1000) == 0


def test_compute_delta_negative_reset() -> None:
    # Counter was reset — return None to signal skip
    assert _compute_delta(current=500, previous=1000) is None


def test_check_anomaly_high_only() -> None:
    # 35 GB today, above 30 GB threshold, but no history (avg=0)
    is_high, is_spike = _check_anomaly(
        bytes_today=35 * 1024**3,
        avg_daily_bytes=0,
        threshold_bytes=30 * 1024**3,
        multiplier=2.0,
    )
    assert is_high is True
    assert is_spike is False


def test_check_anomaly_spike_only() -> None:
    # 20 GB today (below 30 GB threshold), but 3× average (avg=6 GB)
    is_high, is_spike = _check_anomaly(
        bytes_today=20 * 1024**3,
        avg_daily_bytes=6 * 1024**3,
        threshold_bytes=30 * 1024**3,
        multiplier=2.0,
    )
    assert is_high is False
    assert is_spike is True


def test_check_anomaly_both() -> None:
    # 60 GB today, above 30 GB threshold AND 4× average (avg=15 GB)
    is_high, is_spike = _check_anomaly(
        bytes_today=60 * 1024**3,
        avg_daily_bytes=15 * 1024**3,
        threshold_bytes=30 * 1024**3,
        multiplier=2.0,
    )
    assert is_high is True
    assert is_spike is True


def test_check_anomaly_neither() -> None:
    # 10 GB today, below threshold, below multiplier
    is_high, is_spike = _check_anomaly(
        bytes_today=10 * 1024**3,
        avg_daily_bytes=8 * 1024**3,
        threshold_bytes=30 * 1024**3,
        multiplier=2.0,
    )
    assert is_high is False
    assert is_spike is False


def test_check_anomaly_stable_heavy_user() -> None:
    # User consistently uses 50 GB/day — high but NOT a spike
    is_high, is_spike = _check_anomaly(
        bytes_today=50 * 1024**3,
        avg_daily_bytes=50 * 1024**3,
        threshold_bytes=30 * 1024**3,
        multiplier=2.0,
    )
    assert is_high is True   # still flagged as high
    assert is_spike is False  # not a spike (matches their norm)


def test_check_anomaly_zero_average_no_spike() -> None:
    # No history — spike check disabled, only threshold applies
    is_high, is_spike = _check_anomaly(
        bytes_today=5 * 1024**3,
        avg_daily_bytes=0,
        threshold_bytes=30 * 1024**3,
        multiplier=2.0,
    )
    assert is_high is False
    assert is_spike is False

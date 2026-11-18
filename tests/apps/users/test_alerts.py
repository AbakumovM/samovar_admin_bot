from src.apps.users.controllers.scheduler.alerts import (
    format_threshold_alert,
    is_spike,
    make_block_keyboard,
    pick_threshold,
)

GB = 1024**3
TH = [30, 50, 100, 150]


def test_pick_threshold_none_below_lowest() -> None:
    assert pick_threshold(29 * GB, TH, set()) is None


def test_pick_threshold_jump_picks_highest() -> None:
    assert pick_threshold(110 * GB, TH, set()) == 100


def test_pick_threshold_next_level_after_lower_alerted() -> None:
    assert pick_threshold(60 * GB, TH, {30}) == 50


def test_pick_threshold_silent_when_highest_passed_alerted() -> None:
    assert pick_threshold(60 * GB, TH, {30, 50, 100}) is None


def test_is_spike_true_above_multiplier() -> None:
    assert is_spike(60 * GB, 15 * GB, 2.0) is True


def test_is_spike_false_without_history() -> None:
    assert is_spike(20 * GB, 0, 2.0) is False


def test_is_spike_false_below_multiplier() -> None:
    assert is_spike(10 * GB, 8 * GB, 2.0) is False


def test_format_regular_alert_with_spike() -> None:
    text = format_threshold_alert("ivan<1>", int(57.3 * GB), 50, 150, 15.2 * GB, spike=True)
    assert text == (
        "⚠️ Высокий трафик: <b>ivan&lt;1&gt;</b>\n"
        "За сегодня (с 03:00 МСК): 57.3 GB (порог 50 GB)\n"
        "• Резкий скачок ×3.8 (обычно ~15.2 GB/день)"
    )


def test_format_critical_alert_without_spike() -> None:
    text = format_threshold_alert("ivan", int(152.4 * GB), 150, 150, 0.0, spike=False)
    assert text == (
        "🚨 Возможна перепродажа: <b>ivan</b>\nЗа сегодня (с 03:00 МСК): 152.4 GB (порог 150 GB)"
    )


def test_make_block_keyboard_callback() -> None:
    kb = make_block_keyboard("42", 555, int(152.4 * GB))
    assert kb.inline_keyboard[0][0].text == "🚫 Заблокировать"
    assert kb.inline_keyboard[0][0].callback_data == "traffic_block:42:555:152.4"

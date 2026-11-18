import html
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_GB = 1024**3


@dataclass(frozen=True)
class ThresholdAlert:
    user_uuid: str
    username: str
    telegram_id: int
    total_bytes: int
    threshold_gb: int


def fmt_bytes(b: int) -> str:
    gb = b / _GB
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = b / 1024**2
    return f"{mb:.1f} MB"


def pick_threshold(total_bytes: int, thresholds_gb: list[int], alerted_gb: set[int]) -> int | None:
    """Highest crossed threshold, or None if nothing crossed or it was already alerted.

    Lower thresholds are implied by the highest one: once 100 was alerted,
    crossing 30 or 50 again the same day stays silent.
    """
    crossed = [t for t in thresholds_gb if total_bytes > t * _GB]
    if not crossed:
        return None
    highest = max(crossed)
    if highest in alerted_gb:
        return None
    return highest


def is_spike(total_bytes: int, avg_daily_bytes: float, multiplier: float) -> bool:
    return avg_daily_bytes > 0 and total_bytes > multiplier * avg_daily_bytes


def format_threshold_alert(
    username: str,
    total_bytes: int,
    threshold_gb: int,
    critical_threshold_gb: int,
    avg_daily_bytes: float,
    spike: bool,
) -> str:
    safe_username = html.escape(username)
    if threshold_gb >= critical_threshold_gb:
        header = f"🚨 Возможна перепродажа: <b>{safe_username}</b>"
    else:
        header = f"⚠️ Высокий трафик: <b>{safe_username}</b>"
    lines = [
        header,
        f"За сегодня (с 03:00 МСК): {fmt_bytes(total_bytes)} (порог {threshold_gb} GB)",
    ]
    if spike:
        multiplier_actual = total_bytes / avg_daily_bytes
        lines.append(
            f"• Резкий скачок ×{multiplier_actual:.1f} "
            f"(обычно ~{fmt_bytes(int(avg_daily_bytes))}/день)"
        )
    return "\n".join(lines)


def make_block_keyboard(
    remnawave_id: str, telegram_id: int, total_bytes: int
) -> InlineKeyboardMarkup:
    gb = total_bytes / _GB
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"traffic_block:{remnawave_id}:{telegram_id}:{gb:.1f}",
                )
            ]
        ]
    )

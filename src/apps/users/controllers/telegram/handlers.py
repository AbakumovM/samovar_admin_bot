import html
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka.integrations.aiogram import FromDishka, inject

from src.apps.users.application.interfaces.view import UserTrafficView
from src.apps.users.domain.models import UserTrafficDailyInfo

router = Router()

DAYS_MAP = {"day": 1, "week": 7, "month": 30}


def _fmt_bytes(b: int) -> str:
    gb = b / 1024**3
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = b / 1024**2
    return f"{mb:.1f} MB"


def _bar(fraction: float, width: int = 8) -> str:
    filled = round(min(max(fraction, 0.0), 1.0) * width)
    return "█" * filled + "░" * (width - filled)


@router.message(Command("top_traffic"))
@inject
async def cmd_top_traffic(
    message: Message, user_traffic_view: FromDishka[UserTrafficView]
) -> None:
    parts = (message.text or "").split()
    period_key = parts[1] if len(parts) > 1 else "day"
    days = DAYS_MAP.get(period_key, 1)

    records = await user_traffic_view.get_top_traffic(days=days, limit=10)
    if not records:
        await message.answer("Данных о трафике пока нет.")
        return

    label_map = {"day": "24ч", "week": "7 дней", "month": "30 дней"}
    label = label_map.get(period_key, "24ч")
    lines = [f"📊 Топ потребителей трафика ({label})\n"]
    for i, rec in enumerate(records, 1):
        lines.append(f"{i}. <b>{html.escape(rec.username)}</b> — {_fmt_bytes(rec.bytes_consumed)}")
    await message.answer("\n".join(lines))


@router.message(Command("anomalies"))
@inject
async def cmd_anomalies(
    message: Message, user_traffic_view: FromDishka[UserTrafficView]
) -> None:
    records = await user_traffic_view.get_top_traffic_today(limit=50)
    alerted = [r for r in records if r.anomaly_alerted]
    if not alerted:
        await message.answer("⚠️ Аномалий трафика сегодня нет.")
        return

    lines = ["⚠️ Аномалии трафика (сегодня)\n"]
    for rec in alerted:
        lines.append(
            f"<b>{html.escape(rec.username)}</b> — {_fmt_bytes(rec.bytes_consumed)} 🚨"
        )
    await message.answer("\n".join(lines))


@router.message(Command("user_traffic"))
@inject
async def cmd_user_traffic(
    message: Message, user_traffic_view: FromDishka[UserTrafficView]
) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /user_traffic <username>")
        return

    username = parts[1].strip()
    records = await user_traffic_view.get_user_traffic_by_days(username=username, days=7)

    if not records:
        await message.answer(f"Нет данных о трафике для пользователя <b>{html.escape(username)}</b>.")
        return

    # Build a dict for all 7 days including zeros
    today = date.today()
    by_date = {r.date: r.bytes_consumed for r in records}
    max_bytes = max(by_date.values(), default=1)

    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    lines = [f"👤 <b>{html.escape(username)}</b> — трафик за 7 дней\n"]
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        b = by_date.get(d, 0)
        fraction = b / max_bytes if max_bytes > 0 else 0
        anomaly_mark = ""
        matching = [r for r in records if r.date == d and r.anomaly_alerted]
        if matching:
            anomaly_mark = " ⚠️"
        lines.append(
            f"{day_names[d.weekday()]} {d.strftime('%d.%m')}  "
            f"{_fmt_bytes(b):>10} {_bar(fraction)}{anomaly_mark}"
        )

    total = sum(by_date.values())
    lines.append(f"\nИтого: {_fmt_bytes(total)}")
    await message.answer("\n".join(lines))

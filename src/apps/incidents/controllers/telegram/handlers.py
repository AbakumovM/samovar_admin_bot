from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka.integrations.aiogram import FromDishka, inject

from src.apps.incidents.application.interfaces.view import IncidentView
from src.apps.incidents.controllers.scheduler.tasks import _build_daily_report
from src.apps.incidents.domain.models import IncidentInfo

router = Router()


def _fmt_incident(inc: IncidentInfo) -> str:
    status = "🔴 активный" if inc.resolved_at is None else "✅ закрыт"
    downtime = f"{(inc.downtime_seconds or 0) // 60} мин" if inc.resolved_at else "в процессе"
    return (
        f"<b>{inc.node_name}</b> | {status}\n"
        f"  Начало: {inc.started_at.strftime('%d.%m %H:%M')} UTC\n"
        f"  Даунтайм: {downtime}\n"
        f"  Причина: {inc.last_status_message}\n"
        f"  Рестартов: {inc.restart_attempts}"
        + (" | 🚨 эскалация" if inc.escalated else "")
    )


@router.message(Command("incidents"))
@inject
async def cmd_incidents(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    incidents = await incident_view.get_recent_incidents(limit=10)
    if not incidents:
        await message.answer("Инцидентов пока нет.")
        return
    lines = [_fmt_incident(inc) for inc in incidents]
    await message.answer("\n\n".join(lines))


@router.message(Command("stats"))
@inject
async def cmd_stats(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    parts = (message.text or "").split()
    period_map = {"day": 1, "week": 7, "month": 30}
    period_key = parts[1] if len(parts) > 1 else "week"
    days = period_map.get(period_key, 7)

    incidents = await incident_view.get_incidents_by_period(days=days)
    total = len(incidents)
    escalated = sum(1 for i in incidents if i.escalated)
    resolved = [i for i in incidents if i.resolved_at is not None]
    avg_downtime = (
        sum(i.downtime_seconds or 0 for i in resolved) // len(resolved)
        if resolved
        else 0
    )

    label = {"day": "день", "week": "неделю", "month": "месяц"}.get(period_key, "неделю")
    await message.answer(
        f"📊 Статистика за {label}:\n"
        f"Инцидентов: <b>{total}</b>\n"
        f"Эскалаций: <b>{escalated}</b>\n"
        f"Средний даунтайм: <b>{avg_downtime // 60} мин</b>"
    )


@router.message(Command("worst"))
@inject
async def cmd_worst(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    worst = await incident_view.get_worst_nodes(days=30, limit=5)
    if not worst:
        await message.answer("Данных пока нет.")
        return
    lines = []
    for i, (node_uuid, node_name, count, uptime_pct) in enumerate(worst, 1):
        lines.append(f"{i}. <b>{node_name}</b> — {count} инц. | uptime {uptime_pct:.1f}%")
    await message.answer("🔥 Топ проблемных нод (30 дней):\n" + "\n".join(lines))


@router.message(Command("providers"))
@inject
async def cmd_providers(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    incidents = await incident_view.get_incidents_by_period(days=30)
    provider_counts: dict[str, int] = {}
    for inc in incidents:
        prefix = inc.node_name.split("-")[0] if "-" in inc.node_name else inc.node_name
        provider_counts[prefix] = provider_counts.get(prefix, 0) + 1

    if not provider_counts:
        await message.answer("Данных по провайдерам пока нет.")
        return

    lines = [
        f"<b>{prov}</b>: {cnt} инцидентов"
        for prov, cnt in sorted(provider_counts.items(), key=lambda x: -x[1])
    ]
    await message.answer("📡 Инциденты по регионам (30 дней):\n" + "\n".join(lines))


@router.message(Command("report"))
@inject
async def cmd_report(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    incidents = await incident_view.get_incidents_by_period(days=1)
    await message.answer(_build_daily_report(incidents))

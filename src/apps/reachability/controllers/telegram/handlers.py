import logging
from datetime import UTC, datetime, timedelta, timezone

import httpx
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka.integrations.aiogram import FromDishka, inject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.apps.reachability.application.interfaces.view import ReachabilityView
from src.apps.reachability.controllers.scheduler.pass_runner import PointTracker
from src.apps.reachability.controllers.scheduler.tasks import execute_pass
from src.config import Config

logger = logging.getLogger(__name__)

router = Router()

_MSK = timezone(timedelta(hours=3))
_ICONS = {"blocked": "🚫", "partial": "⚠️"}


def _now() -> datetime:
    return datetime.now(UTC)


def _fmt_msk(moment: datetime) -> str:
    return moment.astimezone(_MSK).strftime("%d.%m %H:%M МСК")


@router.message(Command("blocks"))
@inject
async def cmd_blocks(
    message: Message,
    view: FromDishka[ReachabilityView],
    config: FromDishka[Config],
    tracker: FromDishka[PointTracker],
) -> None:
    fresh_since = _now() - timedelta(seconds=3 * config.reachability_interval_seconds)
    rows = await view.list_not_ok(fresh_since)
    lines = []
    for row in rows:
        since = f" — с {_fmt_msk(row.changed_at)}" if row.changed_at else ""
        lines.append(f"{_ICONS.get(row.status, '❔')} {row.ip}{since}")
    if not rows:
        lines.append("✅ Заблокированных IP нет.")
    lines.extend(f"⏸ Точка проверки {name} не работает" for name in tracker.down_points())
    last_checked = await view.last_checked_at()
    footer = (
        f"Последняя проверка: {_fmt_msk(last_checked)}"
        if last_checked is not None
        else "Проверок ещё не было."
    )
    await message.answer("\n".join(lines) + "\n\n" + footer)


@router.message(Command("blocks_check"))
@inject
async def cmd_blocks_check(
    message: Message,
    bot: Bot,
    config: FromDishka[Config],
    session_factory: FromDishka[async_sessionmaker[AsyncSession]],
    raw_client: FromDishka[httpx.AsyncClient],
    tracker: FromDishka[PointTracker],
) -> None:
    if not config.reachability_enabled:
        await message.answer("Проверка блокировок выключена (REACHABILITY_ENABLED=false).")
        return
    if tracker.lock.locked():
        await message.answer("⏳ Проверка уже идёт, результат придёт сводкой.")
        return
    status = await message.answer("⏳ Проверяю…")
    try:
        result = await execute_pass(config, session_factory, raw_client, bot, tracker)
    except Exception as e:
        logger.error("Manual reachability check failed: %r", e)
        await status.edit_text(f"❌ Ошибка проверки: {e}")
        return
    if result.skipped:
        await status.edit_text("⚠️ Проверка пропущена: нет работающих точек")
    else:
        await status.edit_text(f"✅ Проверено IP: {result.checked}, не в порядке: {result.not_ok}")

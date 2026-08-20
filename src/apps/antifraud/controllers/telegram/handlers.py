import logging

import httpx
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject
from remnawave import RemnawaveSDK
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.apps.antifraud.controllers.scheduler.tasks import _run_antifraud_scan
from src.config import Config
from src.infrastructure.geoip.asn import AsnResolver
from src.infrastructure.remnawave.user_cache import UserLookupCache

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("antifraud_check"))
@inject
async def cmd_antifraud_check(
    message: Message,
    bot: Bot,
    config: FromDishka[Config],
    session_factory: FromDishka[async_sessionmaker[AsyncSession]],
    sdk: FromDishka[RemnawaveSDK],
    raw_client: FromDishka[httpx.AsyncClient],
    user_cache: FromDishka[UserLookupCache],
    asn_resolver: FromDishka[AsnResolver],
) -> None:
    status = await message.answer(
        "⏳ Запускаю проверку антифрода (опрос всех нод, может занять пару минут)…"
    )
    try:
        notified = await _run_antifraud_scan(
            config, session_factory, sdk, raw_client, bot, user_cache, asn_resolver
        )
    except Exception as e:
        logger.error("Manual antifraud check failed: %s", e)
        await status.edit_text("⚠️ Проверка завершилась с ошибкой, см. логи бота.")
        return

    if notified == 0:
        await status.edit_text("✅ Проверка завершена: нарушений не найдено.")
    else:
        await status.edit_text(f"✅ Проверка завершена: уведомление отправлено ({notified}) ↑")


@router.callback_query(lambda c: c.data is not None and c.data.startswith("antifraud_drop:"))
@inject
async def callback_drop_connections(
    callback: CallbackQuery,
    raw_client: FromDishka[httpx.AsyncClient],
) -> None:
    remnawave_id = int((callback.data or "").split(":", 1)[1])
    try:
        response = await raw_client.post(
            "/connections/drop",
            json={
                "dropBy": {"by": "userIds", "userIds": [remnawave_id]},
                "targetNodes": {"target": "allNodes"},
            },
        )
        response.raise_for_status()
        await callback.answer("🔌 Отключение запрошено")
    except Exception as e:
        logger.error("Antifraud drop-connections failed for %d: %s", remnawave_id, e)
        await callback.answer("⚠️ Не удалось отправить запрос", show_alert=True)

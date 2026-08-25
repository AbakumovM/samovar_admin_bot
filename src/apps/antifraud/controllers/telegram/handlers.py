import logging

import httpx
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject
from remnawave import RemnawaveSDK
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.apps.antifraud.controllers.scheduler.tasks import (
    _drop_connections,
    _mark_blocked_in_keyboard,
    _run_antifraud_scan,
)
from src.config import Config
from src.infrastructure.geoip.asn import AsnResolver
from src.infrastructure.remnawave.user_cache import UserLookupCache
from src.infrastructure.samovarbot.client import SamovarbotClient, block_user

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
    samovarbot_client: FromDishka[SamovarbotClient],
) -> None:
    status = await message.answer(
        "⏳ Запускаю проверку антифрода (опрос всех нод, может занять пару минут)…"
    )
    try:
        notified = await _run_antifraud_scan(
            config,
            session_factory,
            sdk,
            raw_client,
            bot,
            user_cache,
            asn_resolver,
            samovarbot_client,
        )
    except Exception as e:
        logger.error("Manual antifraud check failed: %s", e)
        await status.edit_text("⚠️ Проверка завершилась с ошибкой, см. логи бота.")
        return

    if notified == 0:
        await status.edit_text("✅ Проверка завершена: нарушений не найдено.")
    else:
        await status.edit_text(f"✅ Проверка завершена: уведомление отправлено ({notified}) ↑")


@router.callback_query(lambda c: c.data == "antifraud_noop")
async def callback_noop(callback: CallbackQuery) -> None:
    await callback.answer("Уже заблокирован ✅")


@router.callback_query(lambda c: c.data is not None and c.data.startswith("antifraud_block:"))
@inject
async def callback_block_user(
    callback: CallbackQuery,
    raw_client: FromDishka[httpx.AsyncClient],
    samovarbot_client: FromDishka[SamovarbotClient],
) -> None:
    parts = (callback.data or "").split(":")
    remnawave_id = int(parts[1])
    telegram_id = int(parts[2])
    reason = f"antifraud: manual block (remnawave_id={remnawave_id})"

    blocked = await block_user(samovarbot_client, telegram_id, reason)
    if not blocked:
        await callback.answer("⚠️ Не удалось заблокировать", show_alert=True)
        return
    await _drop_connections(raw_client, remnawave_id)

    if isinstance(callback.message, Message) and callback.message.reply_markup is not None:
        try:
            new_keyboard = _mark_blocked_in_keyboard(callback.message.reply_markup, remnawave_id)
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        except Exception as e:
            logger.warning("Antifraud: failed to update keyboard after block: %s", e)

    await callback.answer("🚫 Пользователь заблокирован")

import logging
from typing import Any, NewType

import httpx

from src.config import Config

logger = logging.getLogger(__name__)

SamovarbotClient = NewType("SamovarbotClient", httpx.AsyncClient)


def create_samovarbot_client(config: Config) -> SamovarbotClient:
    client = httpx.AsyncClient(
        base_url=config.samovarbot_base_url.rstrip("/"),
        headers={"X-Internal-Api-Key": config.samovarbot_internal_api_key},
        timeout=15,
    )
    return SamovarbotClient(client)


async def check_no_active_payment(client: SamovarbotClient, telegram_id: int) -> bool | None:
    """Критерий 1: нет активной оплаченной подписки прямо сейчас.

    Возвращает True, если подтверждено отсутствие, False, если у
    пользователя есть активная подписка, None, если проверку не удалось
    выполнить (сетевая ошибка, неожиданный статус) — вызывающий код должен
    трактовать None как "неизвестно", никогда как False, чтобы падение
    samovarbot не подавляло критерий молча.
    """
    try:
        response = await client.get(f"/internal/users/{telegram_id}/payment-status")
    except httpx.HTTPError as e:
        logger.warning("Antifraud: payment-status check failed for tg:%d: %s", telegram_id, e)
        return None
    if response.status_code != 200:
        logger.warning(
            "Antifraud: payment-status check for tg:%d returned %d",
            telegram_id,
            response.status_code,
        )
        return None
    payload: dict[str, Any] = response.json()
    return not bool(payload["has_active_subscription"])


async def block_user(client: SamovarbotClient, telegram_id: int, reason: str) -> bool:
    try:
        response = await client.post(
            f"/internal/users/{telegram_id}/block", json={"reason": reason}
        )
    except httpx.HTTPError as e:
        logger.error("Antifraud: block request failed for tg:%d: %s", telegram_id, e)
        return False
    if response.status_code != 200:
        logger.error(
            "Antifraud: block request for tg:%d returned %d", telegram_id, response.status_code
        )
        return False
    return True

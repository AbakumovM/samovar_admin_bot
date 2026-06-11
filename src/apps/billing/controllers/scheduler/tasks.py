import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from remnawave import RemnawaveSDK

from src.apps.billing.adapters.view import RemnawaveBillingView
from src.apps.billing.domain.models import BillingNodeInfo
from src.config import Config

logger = logging.getLogger(__name__)


def _format_billing_alert(node: BillingNodeInfo, currency: str) -> str:
    date_str = node.next_billing_at.strftime("%d.%m.%Y")
    days_text = "сегодня!" if node.days_until == 0 else f"через {node.days_until} дн."
    return (
        f"⚠️ <b>Предстоящий платёж</b>\n\n"
        f"Нода: <b>{node.node_name}</b>\n"
        f"Провайдер: {node.provider_name}\n"
        f"Дата: {date_str} ({days_text})"
    )


def _make_alert_keyboard(node: BillingNodeInfo) -> InlineKeyboardMarkup:
    row = []
    if node.provider_login_url:
        row.append(
            InlineKeyboardButton(text=f"🔗 {node.provider_name}", url=node.provider_login_url)
        )
    row.append(
        InlineKeyboardButton(
            text="✅ Отметить оплату",
            callback_data=f"billing_pay:{node.uuid}",
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def billing_alert_task(config: Config, sdk: RemnawaveSDK, bot: Bot) -> None:
    while True:
        now = datetime.now(UTC)
        next_check = now.replace(
            hour=config.billing_check_hour_utc, minute=0, second=0, microsecond=0
        )
        if next_check <= now:
            next_check += timedelta(days=1)
        sleep_seconds = (next_check - now).total_seconds()
        logger.info(
            "Billing alert check scheduled in %.0fs (at %s UTC)",
            sleep_seconds,
            next_check.strftime("%H:%M"),
        )
        await asyncio.sleep(sleep_seconds)

        try:
            view = RemnawaveBillingView(sdk=sdk)
            nodes = await view.get_billing_nodes()
            for node in nodes:
                if 0 <= node.days_until <= config.billing_alert_days_before:
                    text = _format_billing_alert(node, config.billing_currency)
                    keyboard = _make_alert_keyboard(node)
                    for admin_id in config.admin_ids:
                        try:
                            await bot.send_message(admin_id, text, reply_markup=keyboard)
                        except Exception as e:
                            logger.error("Failed to send billing alert to %s: %s", admin_id, e)
        except Exception as e:
            logger.error("Billing alert check error: %s", e)

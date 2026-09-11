import logging
from datetime import timedelta
from uuid import UUID

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject
from remnawave import RemnawaveSDK
from remnawave.models import UpdateInfraBillingNodeRequestDto

from src.apps.billing.application.interfaces.view import BillingView
from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo
from src.config import Config

logger = logging.getLogger(__name__)

router = Router()


def _format_billing_overview(
    nodes: list[BillingNodeInfo],
    stats: BillingStatsInfo,
    alert_days: int,
    hidden_count: int = 0,
) -> str:
    lines = [
        "💰 <b>Биллинг нод</b>\n",
        f"📊 Предстоящих платежей: {stats.upcoming_nodes_count}",
    ]
    if not nodes and hidden_count == 0:
        lines.append("\nНет зарегистрированных billing-нод.")
        return "\n".join(lines)
    lines.append("\n📅 Платежи на ближайшую неделю:")
    if not nodes:
        lines.append("  Нет платежей в ближайшие 7 дней.")
    for node in nodes:
        icon = "⚠️" if node.days_until <= alert_days else "  "
        date_str = node.next_billing_at.strftime("%d.%m.%Y")
        if node.days_until < 0:
            days_text = f"просрочен на {-node.days_until} дн."
        else:
            days_text = "сегодня!" if node.days_until == 0 else f"через {node.days_until} дн."
        lines.append(
            f"{icon} <b>{node.node_name}</b> ({node.provider_name}) — {date_str} ({days_text})"
        )
    if hidden_count > 0:
        lines.append(f"\n<i>...и ещё {hidden_count} нод позже</i>")
    return "\n".join(lines)


def _make_billing_keyboard(
    nodes: list[BillingNodeInfo], alert_days: int
) -> InlineKeyboardMarkup | None:
    urgent = [n for n in nodes if n.days_until <= alert_days]
    if not urgent:
        return None
    rows = []
    for node in urgent:
        row = []
        if node.provider_login_url:
            row.append(InlineKeyboardButton(text="🔗 Кабинет", url=node.provider_login_url))
        row.append(
            InlineKeyboardButton(
                text=f"✅ {node.node_name}",
                callback_data=f"billing_pay:{node.uuid}",
            )
        )
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


_DISPLAY_DAYS = 7


@router.message(Command("billing"))
@inject
async def cmd_billing(
    message: Message,
    billing_view: FromDishka[BillingView],
    config: FromDishka[Config],
) -> None:
    all_nodes = await billing_view.get_billing_nodes()
    stats = await billing_view.get_billing_stats()
    visible = [n for n in all_nodes if n.days_until <= _DISPLAY_DAYS]
    hidden_count = len(all_nodes) - len(visible)
    text = _format_billing_overview(visible, stats, config.billing_alert_days_before, hidden_count)
    keyboard = _make_billing_keyboard(visible, config.billing_alert_days_before)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data is not None and c.data.startswith("billing_pay:"))
@inject
async def callback_mark_paid(
    callback: CallbackQuery,
    billing_view: FromDishka[BillingView],
    sdk: FromDishka[RemnawaveSDK],
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    billing_node_uuid = (callback.data or "").split(":", 1)[1]
    nodes = await billing_view.get_billing_nodes()
    node = next((n for n in nodes if n.uuid == billing_node_uuid), None)
    if node is None:
        await callback.message.answer("Нода не найдена.")
        return

    new_next = node.next_billing_at + timedelta(days=30)
    await sdk.infra_billing.update_infra_billing_node(
        body=UpdateInfraBillingNodeRequestDto(
            uuids=[UUID(node.uuid)],
            next_billing_at=new_next,
        )
    )
    await callback.message.edit_text(
        f"✅ Оплата отмечена. Следующий платёж: <b>{new_next.strftime('%d.%m.%Y')}</b>"
    )

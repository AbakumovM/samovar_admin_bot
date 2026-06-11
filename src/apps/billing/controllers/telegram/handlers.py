from datetime import UTC, datetime, timedelta
from uuid import UUID

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject
from remnawave import RemnawaveSDK
from remnawave.models import (
    CreateInfraBillingHistoryRecordRequestDto,
    UpdateInfraBillingNodeRequestDto,
)

from src.apps.billing.application.interfaces.view import BillingView
from src.apps.billing.domain.models import BillingNodeInfo, BillingStatsInfo, PaymentRecordInfo
from src.config import Config

router = Router()


class PaymentFSM(StatesGroup):
    waiting_amount = State()
    confirming = State()


def _format_billing_overview(
    nodes: list[BillingNodeInfo],
    stats: BillingStatsInfo,
    currency: str,
    alert_days: int,
) -> str:
    lines = [
        "💰 <b>Биллинг нод</b>\n",
        f"📊 Статистика:\n"
        f"  • Предстоящих платежей: {stats.upcoming_nodes_count}\n"
        f"  • Оплачено за месяц: {stats.current_month_payments:.2f} {currency}\n"
        f"  • Всего потрачено: {stats.total_spent:.2f} {currency}",
    ]
    if not nodes:
        lines.append("\nНет зарегистрированных billing-нод.")
        return "\n".join(lines)
    lines.append("\n📅 Ближайшие платежи:")
    for node in nodes:
        icon = "⚠️" if node.days_until <= alert_days else "  "
        date_str = node.next_billing_at.strftime("%d.%m.%Y")
        days_text = "сегодня!" if node.days_until == 0 else f"через {node.days_until} дн."
        lines.append(
            f"{icon} <b>{node.node_name}</b> ({node.provider_name}) — {date_str} ({days_text})"
        )
    return "\n".join(lines)


def _format_billing_history(records: list[PaymentRecordInfo], currency: str) -> str:
    if not records:
        return "📜 История платежей пуста."
    lines = ["📜 <b>История платежей (последние 10)</b>\n"]
    for record in records:
        date_str = record.payment_date.strftime("%d.%m.%Y")
        lines.append(
            f"• {date_str} | {record.amount:.2f} {currency} | "
            f"{record.node_name} ({record.provider_name})"
        )
    return "\n".join(lines)


def _make_billing_keyboard(nodes: list[BillingNodeInfo]) -> InlineKeyboardMarkup | None:
    if not nodes:
        return None
    rows = []
    for node in nodes:
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


@router.message(Command("billing"))
@inject
async def cmd_billing(
    message: Message,
    billing_view: FromDishka[BillingView],
    config: FromDishka[Config],
) -> None:
    nodes = await billing_view.get_billing_nodes()
    stats = await billing_view.get_billing_stats()
    text = _format_billing_overview(
        nodes, stats, config.billing_currency, config.billing_alert_days_before
    )
    keyboard = _make_billing_keyboard(nodes)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("billing_history"))
@inject
async def cmd_billing_history(
    message: Message,
    billing_view: FromDishka[BillingView],
    config: FromDishka[Config],
) -> None:
    records = await billing_view.get_payment_history(limit=10)
    await message.answer(_format_billing_history(records, config.billing_currency))


@router.callback_query(lambda c: c.data is not None and c.data.startswith("billing_pay:"))
@inject
async def callback_start_payment(
    callback: CallbackQuery,
    state: FSMContext,
    billing_view: FromDishka[BillingView],
    config: FromDishka[Config],
) -> None:
    await callback.answer()
    billing_node_uuid = (callback.data or "").split(":", 1)[1]
    nodes = await billing_view.get_billing_nodes()
    node = next((n for n in nodes if n.uuid == billing_node_uuid), None)
    if node is None:
        await callback.message.answer("Нода не найдена.")  # type: ignore[union-attr]
        return
    await state.update_data(
        billing_node_uuid=billing_node_uuid,
        node_name=node.node_name,
        provider_name=node.provider_name,
        provider_uuid=node.provider_uuid,
        current_next_billing_at=node.next_billing_at.isoformat(),
    )
    await state.set_state(PaymentFSM.waiting_amount)
    await callback.message.answer(  # type: ignore[union-attr]
        f"Оплата ноды <b>{node.node_name}</b> ({node.provider_name}).\n"
        f"Введите сумму в {config.billing_currency}:"
    )


@router.message(StateFilter(PaymentFSM.waiting_amount))
@inject
async def process_payment_amount(
    message: Message,
    state: FSMContext,
    config: FromDishka[Config],
) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число (например: 1500 или 1500.50).")
        return

    data = await state.get_data()
    current_next = datetime.fromisoformat(data["current_next_billing_at"])
    new_next = current_next + timedelta(days=30)
    await state.update_data(amount=amount)
    await state.set_state(PaymentFSM.confirming)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="billing_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="billing_cancel"),
        ]]
    )
    await message.answer(
        f"Записать оплату <b>{amount:.2f} {config.billing_currency}</b> "
        f"для ноды <b>{data['node_name']}</b>?\n"
        f"Следующий платёж: <b>{new_next.strftime('%d.%m.%Y')}</b>",
        reply_markup=keyboard,
    )


@router.callback_query(StateFilter(PaymentFSM.confirming), lambda c: c.data == "billing_confirm")
@inject
async def callback_confirm_payment(
    callback: CallbackQuery,
    state: FSMContext,
    sdk: FromDishka[RemnawaveSDK],
    config: FromDishka[Config],
) -> None:
    await callback.answer()
    data = await state.get_data()
    await state.clear()

    billing_node_uuid = UUID(data["billing_node_uuid"])
    provider_uuid = UUID(data["provider_uuid"])
    amount = float(data["amount"])
    current_next = datetime.fromisoformat(data["current_next_billing_at"])
    new_next = current_next + timedelta(days=30)
    now = datetime.now(UTC)

    await sdk.infra_billing.create_infra_billing_history_record(
        body=CreateInfraBillingHistoryRecordRequestDto(
            provider_uuid=provider_uuid,
            amount=amount,
            billed_at=now,
        )
    )
    await sdk.infra_billing.update_infra_billing_node(
        body=UpdateInfraBillingNodeRequestDto(
            uuids=[billing_node_uuid],
            next_billing_at=new_next,
        )
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Оплата записана. Следующий платёж: <b>{new_next.strftime('%d.%m.%Y')}</b>"
    )


@router.callback_query(StateFilter(PaymentFSM.confirming), lambda c: c.data == "billing_cancel")
async def callback_cancel_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")  # type: ignore[union-attr]

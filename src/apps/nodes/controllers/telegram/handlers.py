from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject

from src.apps.nodes.application.interactor import NodeInteractor
from src.apps.nodes.application.interfaces.view import NodeView
from src.apps.nodes.domain.exceptions import NodeNotFound
from src.apps.nodes.domain.models import NodeInfo

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Remnawave Admin Bot</b>\n\n"
        "Доступные команды:\n"
        "/status — состояние всех нод\n"
        "/node &lt;имя&gt; — детали по ноде\n"
        "/incidents — последние инциденты\n"
        "/stats day|week|month — статистика\n"
        "/worst — топ проблемных нод\n"
        "/providers — инциденты по регионам\n"
        "/restart &lt;имя&gt; — рестарт ноды\n"
        "/restart_all — рестарт всех нод\n"
        "/mute &lt;имя&gt; 30m|1h|24h — заглушить алерты\n"
        "/unmute &lt;имя&gt; — снять мут"
    )


_MUTE_DURATIONS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
}


def _status_icon(node: NodeInfo) -> str:
    if node.is_disabled:
        return "⛔"
    if node.is_connecting:
        return "⏳"
    return "🟢" if node.is_connected else "🔴"


def _format_node_line(node: NodeInfo) -> str:
    icon = _status_icon(node)
    return (
        f"{icon} <b>{node.name}</b> [{node.country_code}] "
        f"{node.provider} — {node.users_online} users"
    )


def _format_node_detail(node: NodeInfo) -> str:
    icon = _status_icon(node)
    uptime_h = node.xray_uptime // 3600
    traffic_gb = node.traffic_used_bytes / (1024**3)
    return (
        f"{icon} <b>{node.name}</b>\n"
        f"Адрес: <code>{node.address}</code>\n"
        f"Страна: {node.country_code} | Провайдер: {node.provider}\n"
        f"Онлайн: {node.users_online} | Трафик: {traffic_gb:.2f} GB\n"
        f"Xray uptime: {uptime_h}h\n"
        f"Статус: {node.last_status_message}"
    )


@router.message(Command("status"))
@inject
async def cmd_status(message: Message, node_view: FromDishka[NodeView]) -> None:
    nodes = await node_view.get_all_nodes()
    if not nodes:
        await message.answer("Нод не найдено.")
        return
    lines = [_format_node_line(n) for n in nodes]
    await message.answer("\n".join(lines))


@router.message(Command("node"))
@inject
async def cmd_node(message: Message, node_view: FromDishka[NodeView]) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /node <имя>")
        return
    name = parts[1]
    node = await node_view.get_node_by_name(name)
    if node is None:
        await message.answer(f"Нода <b>{name}</b> не найдена.")
        return
    await message.answer(_format_node_detail(node))


@router.message(Command("restart"))
@inject
async def cmd_restart(
    message: Message, node_interactor: FromDishka[NodeInteractor]
) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /restart <имя>")
        return
    name = parts[1]
    try:
        node = await node_interactor.restart_node_by_name(name)
        await message.answer(f"✅ Нода <b>{node.name}</b> перезапускается.")
    except NodeNotFound:
        await message.answer(f"Нода <b>{name}</b> не найдена.")


@router.message(Command("restart_all"))
async def cmd_restart_all(message: Message) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, перезапустить все",
                    callback_data="confirm_restart_all",
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_restart_all")],
        ]
    )
    await message.answer("Перезапустить <b>все</b> ноды?", reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "confirm_restart_all")
@inject
async def callback_restart_all(
    callback: CallbackQuery,
    node_view: FromDishka[NodeView],
    node_interactor: FromDishka[NodeInteractor],
) -> None:
    await callback.answer()
    await callback.message.edit_text("⏳ Перезапускаем все ноды...")  # type: ignore[union-attr]
    nodes = await node_view.get_all_nodes()
    for node in nodes:
        try:
            await node_interactor.restart_node_by_name(node.name)
        except NodeNotFound:
            pass
    await callback.message.edit_text(f"✅ Перезапущено {len(nodes)} нод.")  # type: ignore[union-attr]


@router.callback_query(lambda c: c.data == "cancel_restart_all")
async def callback_cancel_restart_all(callback: CallbackQuery) -> None:
    await callback.answer("Отменено.")
    await callback.message.edit_text("Отменено.")  # type: ignore[union-attr]


@router.message(Command("mute"))
@inject
async def cmd_mute(
    message: Message,
    node_view: FromDishka[NodeView],
    node_interactor: FromDishka[NodeInteractor],
) -> None:
    parts = (message.text or "").split()
    if len(parts) < 3 or parts[2] not in _MUTE_DURATIONS:
        await message.answer("Использование: /mute <имя> <30m|1h|24h>")
        return
    name, duration_key = parts[1], parts[2]
    duration = _MUTE_DURATIONS[duration_key]
    node = await node_view.get_node_by_name(name)
    if node is None:
        await message.answer(f"Нода <b>{name}</b> не найдена.")
        return
    admin_id = message.from_user.id if message.from_user else 0
    try:
        await node_interactor.mute_node_by_name(name, duration, admin_telegram_id=admin_id)
        await message.answer(f"🔇 Нода <b>{node.name}</b> замьючена на {duration_key}.")
    except NodeNotFound:
        await message.answer(f"Нода <b>{name}</b> не найдена.")


@router.message(Command("unmute"))
@inject
async def cmd_unmute(
    message: Message, node_interactor: FromDishka[NodeInteractor]
) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /unmute <имя>")
        return
    name = parts[1]
    try:
        node = await node_interactor.unmute_node_by_name(name)
        await message.answer(f"🔔 Мут снят с ноды <b>{node.name}</b>.")
    except NodeNotFound:
        await message.answer(f"Нода <b>{name}</b> не найдена.")

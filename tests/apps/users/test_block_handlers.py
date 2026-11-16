from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import InlineKeyboardMarkup, Message

from src.apps.users.controllers.telegram.handlers import (
    callback_traffic_block,
    callback_traffic_noop,
)

# dishka's @inject strips FromDishka-annotated params — call the original function.
_callback_traffic_block = callback_traffic_block.__dishka_orig_func__  # type: ignore[attr-defined]


def _make_callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.reply_markup = MagicMock()
    callback.message.edit_reply_markup = AsyncMock()
    return callback


async def test_traffic_block_success() -> None:
    callback = _make_callback("traffic_block:42:555:152.4")
    raw_client = MagicMock()
    raw_client.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    samovarbot_client = MagicMock()

    with patch(
        "src.apps.users.controllers.telegram.handlers.block_user",
        AsyncMock(return_value=True),
    ) as block_mock:
        await _callback_traffic_block(callback, raw_client, samovarbot_client)

    block_mock.assert_awaited_once_with(
        samovarbot_client, 555, "traffic: manual block (remnawave_id=42, 24h=152.4 GB)"
    )
    raw_client.post.assert_awaited_once()
    keyboard: InlineKeyboardMarkup = callback.message.edit_reply_markup.await_args.kwargs[
        "reply_markup"
    ]
    assert keyboard.inline_keyboard[0][0].text == "✅ Заблокирован"
    assert keyboard.inline_keyboard[0][0].callback_data == "traffic_noop"
    callback.answer.assert_awaited_once_with("🚫 Пользователь заблокирован")


async def test_traffic_block_failure_does_not_drop() -> None:
    callback = _make_callback("traffic_block:42:555:152.4")
    raw_client = MagicMock()
    raw_client.post = AsyncMock()
    samovarbot_client = MagicMock()

    with patch(
        "src.apps.users.controllers.telegram.handlers.block_user",
        AsyncMock(return_value=False),
    ):
        await _callback_traffic_block(callback, raw_client, samovarbot_client)

    raw_client.post.assert_not_awaited()
    callback.message.edit_reply_markup.assert_not_awaited()
    callback.answer.assert_awaited_once_with("⚠️ Не удалось заблокировать", show_alert=True)


async def test_traffic_noop_answers() -> None:
    callback = _make_callback("traffic_noop")

    await callback_traffic_noop(callback)

    callback.answer.assert_awaited_once_with("Уже заблокирован ✅")

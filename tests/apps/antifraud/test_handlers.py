from unittest.mock import AsyncMock, MagicMock, patch

from src.apps.antifraud.controllers.telegram.handlers import (
    callback_block_user,
    cmd_antifraud_check,
)

# dishka's @inject strips FromDishka-annotated params from the wrapped
# signature and resolves them from a container instead — for a unit test we
# bypass DI entirely and call the original undecorated function directly.
_cmd_antifraud_check = cmd_antifraud_check.__dishka_orig_func__  # type: ignore[attr-defined]
_callback_block_user = callback_block_user.__dishka_orig_func__  # type: ignore[attr-defined]


def _make_callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    return callback


def _make_message() -> MagicMock:
    message = MagicMock()
    status = MagicMock()
    status.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=status)
    return message


async def test_cmd_antifraud_check_reports_no_violations() -> None:
    message = _make_message()
    with patch(
        "src.apps.antifraud.controllers.telegram.handlers._run_antifraud_scan",
        AsyncMock(return_value=0),
    ) as scan:
        await _cmd_antifraud_check(message, *[MagicMock() for _ in range(8)])

    message.answer.assert_awaited_once()
    status = message.answer.return_value
    status.edit_text.assert_awaited_once()
    assert "не найдено" in status.edit_text.await_args.args[0]
    scan.assert_awaited_once()


async def test_cmd_antifraud_check_reports_notified_count() -> None:
    message = _make_message()
    with patch(
        "src.apps.antifraud.controllers.telegram.handlers._run_antifraud_scan",
        AsyncMock(return_value=2),
    ):
        await _cmd_antifraud_check(message, *[MagicMock() for _ in range(8)])

    status = message.answer.return_value
    assert "2" in status.edit_text.await_args.args[0]


async def test_cmd_antifraud_check_reports_error() -> None:
    message = _make_message()
    with patch(
        "src.apps.antifraud.controllers.telegram.handlers._run_antifraud_scan",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await _cmd_antifraud_check(message, *[MagicMock() for _ in range(8)])

    status = message.answer.return_value
    assert "ошибк" in status.edit_text.await_args.args[0].lower()


async def test_callback_block_user_success() -> None:
    callback = _make_callback("antifraud_block:42:555")
    raw_client = MagicMock()
    drop_response = MagicMock()
    drop_response.raise_for_status = MagicMock()
    raw_client.post = AsyncMock(return_value=drop_response)
    samovarbot_client = MagicMock()

    with patch(
        "src.apps.antifraud.controllers.telegram.handlers.block_user",
        AsyncMock(return_value=True),
    ) as block_mock:
        await _callback_block_user(callback, raw_client, samovarbot_client)

    block_mock.assert_awaited_once_with(
        samovarbot_client, 555, "antifraud: manual block (remnawave_id=42)"
    )
    raw_client.post.assert_awaited_once()  # _drop_connections был вызван
    callback.answer.assert_awaited_once()
    assert "заблокирован" in callback.answer.await_args.args[0]


async def test_callback_block_user_failure_does_not_drop_connections() -> None:
    callback = _make_callback("antifraud_block:42:555")
    raw_client = MagicMock()
    raw_client.post = AsyncMock()
    samovarbot_client = MagicMock()

    with patch(
        "src.apps.antifraud.controllers.telegram.handlers.block_user",
        AsyncMock(return_value=False),
    ):
        await _callback_block_user(callback, raw_client, samovarbot_client)

    raw_client.post.assert_not_awaited()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    assert "не удалось" in callback.answer.await_args.args[0].lower()


async def test_callback_block_user_parses_remnawave_and_telegram_ids() -> None:
    callback = _make_callback("antifraud_block:42:555")
    raw_client = MagicMock()
    raw_client.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    samovarbot_client = MagicMock()

    with patch(
        "src.apps.antifraud.controllers.telegram.handlers.block_user",
        AsyncMock(return_value=True),
    ) as block_mock:
        await _callback_block_user(callback, raw_client, samovarbot_client)

    # block_user вызывается с telegram_id (555), не с remnawave_id (42)
    assert block_mock.await_args.args[1] == 555
    # _drop_connections (через raw_client.post) использует remnawave_id (42)
    raw_client.post.assert_awaited_once_with(
        "/connections/drop",
        json={"dropBy": {"by": "userIds", "userIds": [42]}, "targetNodes": {"target": "allNodes"}},
    )

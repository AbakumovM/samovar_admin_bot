from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.apps.antifraud.controllers.telegram.handlers import (
    callback_drop_connections,
    cmd_antifraud_check,
)

# dishka's @inject strips FromDishka-annotated params from the wrapped
# signature and resolves them from a container instead — for a unit test we
# bypass DI entirely and call the original undecorated function directly.
_callback_drop_connections = callback_drop_connections.__dishka_orig_func__  # type: ignore[attr-defined]
_cmd_antifraud_check = cmd_antifraud_check.__dishka_orig_func__  # type: ignore[attr-defined]


def _make_callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    return callback


async def test_callback_drop_connections_success() -> None:
    callback = _make_callback("antifraud_drop:42")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    raw_client = MagicMock()
    raw_client.post = AsyncMock(return_value=response)

    await _callback_drop_connections(callback, raw_client)

    raw_client.post.assert_awaited_once_with(
        "/connections/drop",
        json={"dropBy": {"by": "userIds", "userIds": [42]}, "targetNodes": {"target": "allNodes"}},
    )
    callback.answer.assert_awaited_once()
    assert "запрошено" in callback.answer.await_args.args[0]


async def test_callback_drop_connections_http_error_shows_alert() -> None:
    callback = _make_callback("antifraud_drop:42")
    raw_client = MagicMock()
    raw_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock())
    )

    await _callback_drop_connections(callback, raw_client)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True


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
        await _cmd_antifraud_check(message, *[MagicMock() for _ in range(7)])

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
        await _cmd_antifraud_check(message, *[MagicMock() for _ in range(7)])

    status = message.answer.return_value
    assert "2" in status.edit_text.await_args.args[0]


async def test_cmd_antifraud_check_reports_error() -> None:
    message = _make_message()
    with patch(
        "src.apps.antifraud.controllers.telegram.handlers._run_antifraud_scan",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await _cmd_antifraud_check(message, *[MagicMock() for _ in range(7)])

    status = message.answer.return_value
    assert "ошибк" in status.edit_text.await_args.args[0].lower()

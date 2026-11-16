from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.apps.reachability.controllers.scheduler.pass_runner import PassResult, PointTracker
from src.apps.reachability.controllers.telegram.handlers import cmd_blocks, cmd_blocks_check
from src.apps.reachability.domain.models import IpStateRow

_cmd_blocks = cmd_blocks.__dishka_orig_func__  # type: ignore[attr-defined]
_cmd_blocks_check = cmd_blocks_check.__dishka_orig_func__  # type: ignore[attr-defined]


def _message() -> MagicMock:
    message = MagicMock()
    status = MagicMock()
    status.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=status)
    return message


async def test_blocks_empty() -> None:
    message = _message()
    view = MagicMock()
    view.list_not_ok = AsyncMock(return_value=[])
    view.last_checked_at = AsyncMock(return_value=None)

    await _cmd_blocks(message, view, MagicMock(reachability_interval_seconds=600), PointTracker())

    message.answer.assert_awaited_once_with("✅ Заблокированных IP нет.\n\nПроверок ещё не было.")


async def test_blocks_lists_blocked_ip_in_msk() -> None:
    message = _message()
    view = MagicMock()
    view.list_not_ok = AsyncMock(
        return_value=[
            IpStateRow(
                ip="157.22.177.33",
                status="blocked",
                last_results={},
                changed_at=datetime(2026, 11, 16, 11, 20, tzinfo=UTC),
                checked_at=datetime(2026, 11, 16, 11, 30, tzinfo=UTC),
            )
        ]
    )
    view.last_checked_at = AsyncMock(return_value=datetime(2026, 11, 16, 11, 30, tzinfo=UTC))

    tracker = PointTracker()
    tracker.observe("TW2", False, 1)
    with patch(
        "src.apps.reachability.controllers.telegram.handlers._now",
        return_value=datetime(2026, 11, 16, 11, 35, tzinfo=UTC),
    ):
        await _cmd_blocks(message, view, MagicMock(reachability_interval_seconds=600), tracker)

    message.answer.assert_awaited_once_with(
        "🚫 157.22.177.33 — с 16.11 14:20 МСК\n"
        "⏸ Точка проверки TW2 не работает\n\n"
        "Последняя проверка: 16.11 14:30 МСК"
    )
    # only rows checked within the last 3 intervals count as current
    assert view.list_not_ok.await_args.args[0] == datetime(
        2026, 11, 16, 11, 35, tzinfo=UTC
    ) - timedelta(seconds=1800)


async def test_blocks_check_disabled() -> None:
    message = _message()
    config = MagicMock(reachability_enabled=False)

    await _cmd_blocks_check(message, MagicMock(), config, MagicMock(), MagicMock(), PointTracker())

    message.answer.assert_awaited_once_with(
        "Проверка блокировок выключена (REACHABILITY_ENABLED=false)."
    )


async def test_blocks_check_reports_counts() -> None:
    message = _message()
    config = MagicMock(reachability_enabled=True)
    with patch(
        "src.apps.reachability.controllers.telegram.handlers.execute_pass",
        AsyncMock(return_value=PassResult(checked=25, not_ok=2, skipped=False, messages=[])),
    ):
        await _cmd_blocks_check(
            message, MagicMock(), config, MagicMock(), MagicMock(), PointTracker()
        )

    message.answer.return_value.edit_text.assert_awaited_once_with(
        "✅ Проверено IP: 25, не в порядке: 2"
    )


async def test_blocks_check_skipped() -> None:
    message = _message()
    config = MagicMock(reachability_enabled=True)
    with patch(
        "src.apps.reachability.controllers.telegram.handlers.execute_pass",
        AsyncMock(return_value=PassResult(checked=0, not_ok=0, skipped=True, messages=[])),
    ):
        await _cmd_blocks_check(
            message, MagicMock(), config, MagicMock(), MagicMock(), PointTracker()
        )

    message.answer.return_value.edit_text.assert_awaited_once_with(
        "⚠️ Проверка пропущена: нет работающих точек"
    )


async def test_blocks_check_when_pass_running() -> None:
    message = _message()
    tracker = PointTracker()
    await tracker.lock.acquire()
    with patch(
        "src.apps.reachability.controllers.telegram.handlers.execute_pass", AsyncMock()
    ) as run:
        await _cmd_blocks_check(
            message,
            MagicMock(),
            MagicMock(reachability_enabled=True),
            MagicMock(),
            MagicMock(),
            tracker,
        )
    run.assert_not_awaited()
    message.answer.assert_awaited_once_with("⏳ Проверка уже идёт, результат придёт сводкой.")

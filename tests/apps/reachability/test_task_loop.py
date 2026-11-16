from unittest.mock import AsyncMock, MagicMock, patch

from src.apps.reachability.controllers.scheduler.pass_runner import PassResult, PointTracker
from src.apps.reachability.controllers.scheduler.tasks import run_scheduled_pass

_OK = PassResult(checked=1, not_ok=0, skipped=False, messages=[])


async def _once(tracker: PointTracker, side_effect: object) -> list[str]:
    with patch(
        "src.apps.reachability.controllers.scheduler.tasks.execute_pass",
        AsyncMock(side_effect=side_effect),
    ):
        return await run_scheduled_pass(MagicMock(), MagicMock(), MagicMock(), MagicMock(), tracker)


async def test_pass_failures_alert_after_three_and_once() -> None:
    tracker = PointTracker()
    assert await _once(tracker, RuntimeError("boom")) == []
    assert await _once(tracker, RuntimeError("boom")) == []
    assert await _once(tracker, RuntimeError("<x>")) == [
        "⚠️ Проверка блокировок падает с ошибкой 3 раза подряд: RuntimeError('&lt;x&gt;')"
    ]
    assert await _once(tracker, RuntimeError("boom")) == []


async def test_pass_recovery_message() -> None:
    tracker = PointTracker()
    for _ in range(3):
        await _once(tracker, RuntimeError("boom"))
    assert await _once(tracker, [_OK]) == ["✅ Проверка блокировок снова работает"]
    assert await _once(tracker, [_OK]) == []

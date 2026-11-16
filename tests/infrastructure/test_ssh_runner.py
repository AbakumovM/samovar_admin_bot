import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.reachability.ssh_runner import ProbePoint, run_remote_probe

POINT = ProbePoint(name="RU-10", host="193.233.245.212")
TARGETS = [
    {"ip": "1.1.1.1", "port": 443, "sni": None},
    {"ip": "2.2.2.2", "port": 443, "sni": "x.com"},
]


def _patch_connect(run: AsyncMock) -> Any:
    conn = MagicMock()
    conn.run = run

    @asynccontextmanager
    async def fake_connect(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield conn

    return patch("src.infrastructure.reachability.ssh_runner.asyncssh.connect", fake_connect)


def _completed(stdout: str, exit_status: int = 0) -> MagicMock:
    return MagicMock(stdout=stdout, exit_status=exit_status)


async def _call(timeout: float = 5.0) -> list[dict[str, Any]] | None:
    return await run_remote_probe(POINT, TARGETS, "root", "/k", "/kh", timeout)


async def test_valid_response_returned_and_input_is_targets_json() -> None:
    body = [{"ip": t["ip"], "port": 443, "result": "ok", "ms": 5} for t in TARGETS]
    run = AsyncMock(return_value=_completed(json.dumps(body)))
    with _patch_connect(run):
        assert await _call() == body
    assert json.loads(run.await_args.kwargs["input"]) == TARGETS


async def test_garbage_stdout_is_none() -> None:
    with _patch_connect(AsyncMock(return_value=_completed("garbage"))):
        assert await _call() is None


async def test_wrong_length_is_none() -> None:
    with _patch_connect(AsyncMock(return_value=_completed("[]"))):
        assert await _call() is None


async def test_item_without_result_is_none() -> None:
    body = [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2"}]
    with _patch_connect(AsyncMock(return_value=_completed(json.dumps(body)))):
        assert await _call() is None


async def test_nonzero_exit_is_none() -> None:
    with _patch_connect(AsyncMock(return_value=_completed('{"error": "x"}', 2))):
        assert await _call() is None


async def test_connect_error_is_none() -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("unreachable")

    with patch("src.infrastructure.reachability.ssh_runner.asyncssh.connect", boom):
        assert await _call() is None


async def test_hanging_run_times_out() -> None:
    async def hang(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(10)

    with _patch_connect(AsyncMock(side_effect=hang)):
        assert await _call(timeout=0.05) is None

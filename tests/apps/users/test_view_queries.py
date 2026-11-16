from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from src.apps.users.adapters.view import PostgresUserTrafficView

# asyncpg caps a query at 32767 bind parameters; an IN-list of every active
# user would cross it, so the uuid list must travel as a single array param.
_MANY_UUIDS = [str(i) for i in range(40_000)]


def _captured_param_count(session: MagicMock) -> int:
    stmt = session.execute.await_args.args[0]
    compiled = stmt.compile(
        dialect=postgresql.asyncpg.dialect(), compile_kwargs={"render_postcompile": True}
    )
    return len(compiled.params)


def _session() -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.all = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=result)
    return session


async def test_get_traffic_since_uses_single_array_param() -> None:
    session = _session()

    await PostgresUserTrafficView(session).get_traffic_since(_MANY_UUIDS, datetime.now(UTC))

    assert _captured_param_count(session) <= 2


async def test_get_alerted_thresholds_since_uses_single_array_param() -> None:
    session = _session()

    await PostgresUserTrafficView(session).get_alerted_thresholds_since(
        _MANY_UUIDS, datetime.now(UTC)
    )

    assert _captured_param_count(session) <= 2

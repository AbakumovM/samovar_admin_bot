from datetime import UTC, date, datetime
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


async def test_get_traffic_on_uses_single_array_param() -> None:
    session = _session()

    await PostgresUserTrafficView(session).get_traffic_on(_MANY_UUIDS, date.today())

    assert _captured_param_count(session) <= 2


async def test_get_alerted_thresholds_since_uses_single_array_param() -> None:
    session = _session()

    await PostgresUserTrafficView(session).get_alerted_thresholds_since(
        _MANY_UUIDS, datetime.now(UTC)
    )

    assert _captured_param_count(session) <= 2


async def test_get_alerted_today_filters_alerted_before_limit() -> None:
    session = _session()
    session.execute.return_value.scalars = MagicMock(return_value=MagicMock(all=lambda: []))

    await PostgresUserTrafficView(session).get_alerted_today(limit=50)

    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.asyncpg.dialect()))
    assert "anomaly_alerted IS true" in sql
    assert "LIMIT" in sql

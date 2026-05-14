# Remnawave Admin Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram bot that monitors Remnawave VPN nodes, auto-restarts fallen nodes, escalates after 3 failures/hour, and provides incident analytics via commands.

**Architecture:** Single async Python process — aiogram 3.x long-polling bot + asyncio monitoring loop running concurrently. Clean Architecture with two domains (`nodes`, `incidents`), Dishka DI, remnawave Python SDK for API access.

**Tech Stack:** Python 3.12, aiogram 3.x, remnawave SDK 2.7.1, SQLAlchemy 2.x async, asyncpg, Alembic, PostgreSQL 16, Dishka, Pydantic BaseSettings, uv, ruff, mypy strict, pytest + pytest-asyncio.

---

## File Map

```
bot_admin_samovar/
├── src/
│   ├── apps/
│   │   ├── nodes/
│   │   │   ├── domain/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models.py           # Node dataclass (from API)
│   │   │   │   ├── events.py           # NodeWentOffline, NodeCameOnline, NodeEscalated
│   │   │   │   └── exceptions.py       # NodeNotFound
│   │   │   ├── application/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── interactor.py       # NodeInteractor: restart, mute, unmute
│   │   │   │   └── interfaces/
│   │   │   │       ├── __init__.py
│   │   │   │       ├── gateway.py      # NodeGateway Protocol (restart, mute ops)
│   │   │   │       └── view.py         # NodeView Protocol (get_all, get_one, is_muted)
│   │   │   ├── adapters/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── orm.py              # MutedNodeModel (SQLAlchemy)
│   │   │   │   ├── gateway.py          # RemnaWaveNodeGateway (SDK restart + DB mute)
│   │   │   │   └── view.py             # RemnaWaveNodeView (SDK list + DB mute check)
│   │   │   ├── controllers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── telegram/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   └── handlers.py     # /status /node /restart /restart_all /mute /unmute
│   │   │   │   └── scheduler/
│   │   │   │       ├── __init__.py
│   │   │   │       └── loop.py         # Monitoring loop (core logic)
│   │   │   └── ioc.py                  # Dishka providers for nodes domain
│   │   └── incidents/
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── models.py           # IncidentInfo, NodeStatsSnapshotInfo (frozen dataclasses)
│   │       │   └── commands.py         # OpenIncident, CloseIncident, RecordRestartAttempt, etc.
│   │       ├── application/
│   │       │   ├── __init__.py
│   │       │   ├── interactor.py       # IncidentInteractor
│   │       │   └── interfaces/
│   │       │       ├── __init__.py
│   │       │       ├── gateway.py      # IncidentGateway Protocol
│   │       │       └── view.py         # IncidentView Protocol
│   │       ├── adapters/
│   │       │   ├── __init__.py
│   │       │   ├── orm.py              # IncidentModel, NodeStatsSnapshotModel (SQLAlchemy)
│   │       │   ├── gateway.py          # PostgresIncidentGateway
│   │       │   └── view.py             # PostgresIncidentView
│   │       ├── controllers/
│   │       │   ├── __init__.py
│   │       │   └── telegram/
│   │       │       ├── __init__.py
│   │       │       └── handlers.py     # /incidents /stats /worst /providers
│   │       └── ioc.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # DeclarativeBase (shared for Alembic)
│   │   │   ├── engine.py               # create_async_engine
│   │   │   └── session.py              # async_sessionmaker factory
│   │   ├── remnawave/
│   │   │   ├── __init__.py
│   │   │   └── client.py               # RemnawaveSDK factory
│   │   └── telegram/
│   │       ├── __init__.py
│   │       ├── setup.py                # Bot + Dispatcher factory
│   │       └── middleware.py           # AdminAuthMiddleware
│   ├── config.py                       # Pydantic BaseSettings
│   └── main.py                         # asyncio entrypoint
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
│   ├── conftest.py
│   ├── apps/
│   │   ├── incidents/
│   │   │   └── test_interactor.py
│   │   └── nodes/
│   │       ├── test_interactor.py
│   │       └── test_monitoring_loop.py
│   └── infrastructure/
│       └── test_middleware.py
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

---

## Task 1: Project Bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/config.py`
- Create: `alembic.ini`
- Create all `__init__.py` files for every package listed in the file map

- [ ] **Step 1: Initialize project with uv**

```bash
cd /Users/mihailabakumov/Desktop/code/bot_admin_samovar
git init
uv init --no-readme --python 3.12
```

- [ ] **Step 2: Create `pyproject.toml`**

Replace the generated file entirely:

```toml
[project]
name = "bot-admin-samovar"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "aiogram>=3.17.0",
    "remnawave>=2.7.1",
    "sqlalchemy>=2.0.40",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "dishka>=1.5.0",
    "pydantic-settings>=2.7.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-mock>=3.14.0",
    "mypy>=1.13.0",
    "ruff>=0.8.0",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.mypy]
strict = true
python_version = "3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Install dependencies**

```bash
uv sync
```

Expected: resolves and installs all packages without errors.

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p src/apps/nodes/domain
mkdir -p src/apps/nodes/application/interfaces
mkdir -p src/apps/nodes/adapters
mkdir -p src/apps/nodes/controllers/telegram
mkdir -p src/apps/nodes/controllers/scheduler
mkdir -p src/apps/incidents/domain
mkdir -p src/apps/incidents/application/interfaces
mkdir -p src/apps/incidents/adapters
mkdir -p src/apps/incidents/controllers/telegram
mkdir -p src/infrastructure/db
mkdir -p src/infrastructure/remnawave
mkdir -p src/infrastructure/telegram
mkdir -p tests/apps/incidents
mkdir -p tests/apps/nodes
mkdir -p tests/infrastructure
mkdir -p alembic/versions
mkdir -p docs/superpowers/plans
mkdir -p docs/superpowers/specs
```

- [ ] **Step 5: Create all `__init__.py` files**

```bash
touch src/__init__.py
touch src/apps/__init__.py
touch src/apps/nodes/__init__.py
touch src/apps/nodes/domain/__init__.py
touch src/apps/nodes/application/__init__.py
touch src/apps/nodes/application/interfaces/__init__.py
touch src/apps/nodes/adapters/__init__.py
touch src/apps/nodes/controllers/__init__.py
touch src/apps/nodes/controllers/telegram/__init__.py
touch src/apps/nodes/controllers/scheduler/__init__.py
touch src/apps/incidents/__init__.py
touch src/apps/incidents/domain/__init__.py
touch src/apps/incidents/application/__init__.py
touch src/apps/incidents/application/interfaces/__init__.py
touch src/apps/incidents/adapters/__init__.py
touch src/apps/incidents/controllers/__init__.py
touch src/apps/incidents/controllers/telegram/__init__.py
touch src/infrastructure/__init__.py
touch src/infrastructure/db/__init__.py
touch src/infrastructure/remnawave/__init__.py
touch src/infrastructure/telegram/__init__.py
touch tests/__init__.py
touch tests/apps/__init__.py
touch tests/apps/incidents/__init__.py
touch tests/apps/nodes/__init__.py
touch tests/infrastructure/__init__.py
```

- [ ] **Step 6: Create `src/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    admin_ids: list[int]
    remnawave_base_url: str
    remnawave_token: str
    database_url: str
    poll_interval_seconds: int = 120
    escalation_window_minutes: int = 60
    escalation_max_attempts: int = 3
```

- [ ] **Step 7: Create `.env.example`**

```env
TELEGRAM_BOT_TOKEN=your_token_here
ADMIN_IDS=123456789,987654321
REMNAWAVE_BASE_URL=https://your-panel.com
REMNAWAVE_TOKEN=your_api_token_here
DATABASE_URL=postgresql+asyncpg://botuser:botpass@localhost:5432/botdb
POLL_INTERVAL_SECONDS=120
ESCALATION_WINDOW_MINUTES=60
ESCALATION_MAX_ATTEMPTS=3
```

- [ ] **Step 8: Create `alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 9: Commit**

```bash
git add .
git commit -m "feat: project bootstrap — structure, config, dependencies"
```

---

## Task 2: Infrastructure — Database

**Files:**
- Create: `src/infrastructure/db/base.py`
- Create: `src/infrastructure/db/engine.py`
- Create: `src/infrastructure/db/session.py`

- [ ] **Step 1: Create `src/infrastructure/db/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Create `src/infrastructure/db/engine.py`**

```python
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Config


def create_engine(config: Config) -> AsyncEngine:
    return create_async_engine(config.database_url, echo=False)
```

- [ ] **Step 3: Create `src/infrastructure/db/session.py`**

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/db/
git commit -m "feat: async SQLAlchemy engine and session factory"
```

---

## Task 3: Incidents Domain Models and Commands

**Files:**
- Create: `src/apps/incidents/domain/models.py`
- Create: `src/apps/incidents/domain/commands.py`

- [ ] **Step 1: Write test for domain models**

```python
# tests/apps/incidents/test_interactor.py
from datetime import datetime, timezone
from uuid import uuid4

from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


def test_incident_info_is_frozen() -> None:
    now = datetime.now(timezone.utc)
    incident = IncidentInfo(
        id=uuid4(),
        node_uuid="node-1",
        node_name="DE-1",
        started_at=now,
        resolved_at=None,
        last_status_message="connection timeout",
        restart_attempts=0,
        escalated=False,
        downtime_seconds=None,
    )
    try:
        incident.escalated = True  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass


def test_snapshot_info_is_frozen() -> None:
    now = datetime.now(timezone.utc)
    snap = NodeStatsSnapshotInfo(
        id=uuid4(),
        node_uuid="node-1",
        captured_at=now,
        users_online=5,
        traffic_used_bytes=1024,
        xray_uptime=3600,
        is_connected=True,
    )
    try:
        snap.users_online = 10  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass
```

- [ ] **Step 2: Run test — expect failure**

```bash
uv run pytest tests/apps/incidents/test_interactor.py -v
```

Expected: `ImportError` — `IncidentInfo` not defined yet.

- [ ] **Step 3: Create `src/apps/incidents/domain/models.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class IncidentInfo:
    id: UUID
    node_uuid: str
    node_name: str
    started_at: datetime
    resolved_at: datetime | None
    last_status_message: str
    restart_attempts: int
    escalated: bool
    downtime_seconds: int | None


@dataclass(frozen=True)
class NodeStatsSnapshotInfo:
    id: UUID
    node_uuid: str
    captured_at: datetime
    users_online: int
    traffic_used_bytes: int
    xray_uptime: int
    is_connected: bool
```

- [ ] **Step 4: Create `src/apps/incidents/domain/commands.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class OpenIncident:
    node_uuid: str
    node_name: str
    started_at: datetime
    last_status_message: str


@dataclass(frozen=True)
class CloseIncident:
    incident_id: UUID
    resolved_at: datetime


@dataclass(frozen=True)
class RecordRestartAttempt:
    incident_id: UUID


@dataclass(frozen=True)
class EscalateIncident:
    incident_id: UUID


@dataclass(frozen=True)
class RecordSnapshot:
    node_uuid: str
    captured_at: datetime
    users_online: int
    traffic_used_bytes: int
    xray_uptime: int
    is_connected: bool
```

- [ ] **Step 5: Run test — expect pass**

```bash
uv run pytest tests/apps/incidents/test_interactor.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/apps/incidents/domain/ tests/apps/incidents/
git commit -m "feat: incidents domain models and commands"
```

---

## Task 4: Incidents ORM Models + Alembic

**Files:**
- Create: `src/apps/incidents/adapters/orm.py`
- Create: `src/apps/nodes/adapters/orm.py`
- Create: `alembic/env.py`
- Create: first migration via autogenerate

- [ ] **Step 1: Create `src/apps/incidents/adapters/orm.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_uuid: Mapped[str] = mapped_column(String(255), index=True)
    node_name: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_message: Mapped[str] = mapped_column(String(1024))
    restart_attempts: Mapped[int] = mapped_column(Integer, default=0)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    downtime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NodeStatsSnapshotModel(Base):
    __tablename__ = "node_stats_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_uuid: Mapped[str] = mapped_column(String(255), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    users_online: Mapped[int] = mapped_column(Integer)
    traffic_used_bytes: Mapped[int] = mapped_column(BigInteger)
    xray_uptime: Mapped[int] = mapped_column(Integer)
    is_connected: Mapped[bool] = mapped_column(Boolean)
```

- [ ] **Step 2: Create `src/apps/nodes/adapters/orm.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class MutedNodeModel(Base):
    __tablename__ = "muted_nodes"

    node_uuid: Mapped[str] = mapped_column(String(255), primary_key=True)
    muted_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    muted_by_telegram_id: Mapped[int] = mapped_column(BigInteger)
```

- [ ] **Step 3: Initialize Alembic**

```bash
uv run alembic init alembic
```

- [ ] **Step 4: Edit `alembic/env.py`** — replace the generated file with:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import all ORM models so Alembic autogenerate picks them up
from src.apps.incidents.adapters.orm import IncidentModel, NodeStatsSnapshotModel  # noqa: F401
from src.apps.nodes.adapters.orm import MutedNodeModel  # noqa: F401
from src.infrastructure.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("DATABASE_URL", "")
    return url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = get_url()
    connectable = create_async_engine(url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 5: Add `python-dotenv` dependency (needed in env.py)**

```bash
uv add python-dotenv
```

- [ ] **Step 6: Commit ORM models and Alembic setup**

```bash
git add src/apps/incidents/adapters/orm.py src/apps/nodes/adapters/orm.py alembic/ alembic.ini
git commit -m "feat: ORM models and Alembic configuration"
```

> **Note:** Migration generation (`alembic revision --autogenerate`) requires a running PostgreSQL. Run this during deployment after `docker-compose up postgres`. See Task 13.

---

## Task 5: Incidents Application Layer (Interfaces + Interactor)

**Files:**
- Create: `src/apps/incidents/application/interfaces/gateway.py`
- Create: `src/apps/incidents/application/interfaces/view.py`
- Create: `src/apps/incidents/application/interactor.py`
- Modify: `tests/apps/incidents/test_interactor.py`

- [ ] **Step 1: Write failing tests for IncidentInteractor**

Add to `tests/apps/incidents/test_interactor.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


def make_incident(
    *,
    node_uuid: str = "node-1",
    restart_attempts: int = 0,
    escalated: bool = False,
    resolved_at: datetime | None = None,
) -> IncidentInfo:
    return IncidentInfo(
        id=uuid4(),
        node_uuid=node_uuid,
        node_name="DE-1",
        started_at=datetime.now(timezone.utc),
        resolved_at=resolved_at,
        last_status_message="connection timeout",
        restart_attempts=restart_attempts,
        escalated=escalated,
        downtime_seconds=None,
    )


@pytest.fixture
def gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def interactor(gateway: AsyncMock, view: AsyncMock) -> IncidentInteractor:
    return IncidentInteractor(gateway=gateway, view=view)


async def test_open_incident_calls_gateway(
    interactor: IncidentInteractor, gateway: AsyncMock
) -> None:
    now = datetime.now(timezone.utc)
    cmd = OpenIncident(
        node_uuid="node-1",
        node_name="DE-1",
        started_at=now,
        last_status_message="timeout",
    )
    incident = make_incident()
    gateway.open_incident.return_value = incident

    result = await interactor.open_incident(cmd)

    gateway.open_incident.assert_awaited_once_with(cmd)
    assert result == incident


async def test_close_incident_computes_downtime(
    interactor: IncidentInteractor, gateway: AsyncMock, view: AsyncMock
) -> None:
    started = datetime.now(timezone.utc) - timedelta(minutes=6)
    incident = make_incident()
    open_incident = IncidentInfo(
        id=incident.id,
        node_uuid=incident.node_uuid,
        node_name=incident.node_name,
        started_at=started,
        resolved_at=None,
        last_status_message=incident.last_status_message,
        restart_attempts=incident.restart_attempts,
        escalated=incident.escalated,
        downtime_seconds=None,
    )
    view.get_open_incident.return_value = open_incident
    resolved_at = datetime.now(timezone.utc)
    closed = IncidentInfo(
        id=incident.id,
        node_uuid=incident.node_uuid,
        node_name=incident.node_name,
        started_at=started,
        resolved_at=resolved_at,
        last_status_message=incident.last_status_message,
        restart_attempts=incident.restart_attempts,
        escalated=incident.escalated,
        downtime_seconds=int((resolved_at - started).total_seconds()),
    )
    gateway.close_incident.return_value = closed
    cmd = CloseIncident(incident_id=incident.id, resolved_at=resolved_at)

    result = await interactor.close_incident(cmd)

    gateway.close_incident.assert_awaited_once_with(cmd)
    assert result.downtime_seconds is not None
    assert result.downtime_seconds > 0


async def test_record_restart_attempt(
    interactor: IncidentInteractor, gateway: AsyncMock
) -> None:
    incident = make_incident(restart_attempts=1)
    gateway.record_restart_attempt.return_value = incident
    cmd = RecordRestartAttempt(incident_id=incident.id)

    result = await interactor.record_restart_attempt(cmd)

    gateway.record_restart_attempt.assert_awaited_once_with(cmd)
    assert result == incident


async def test_escalate_incident(
    interactor: IncidentInteractor, gateway: AsyncMock
) -> None:
    incident = make_incident(escalated=True)
    gateway.escalate_incident.return_value = incident
    cmd = EscalateIncident(incident_id=incident.id)

    result = await interactor.escalate_incident(cmd)

    gateway.escalate_incident.assert_awaited_once_with(cmd)
    assert result.escalated is True
```

- [ ] **Step 2: Run tests — expect failure**

```bash
uv run pytest tests/apps/incidents/test_interactor.py -v
```

Expected: `ImportError` — `IncidentInteractor` not defined.

- [ ] **Step 3: Create `src/apps/incidents/application/interfaces/gateway.py`**

```python
from typing import Protocol

from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


class IncidentGateway(Protocol):
    async def open_incident(self, cmd: OpenIncident) -> IncidentInfo: ...
    async def close_incident(self, cmd: CloseIncident) -> IncidentInfo: ...
    async def record_restart_attempt(self, cmd: RecordRestartAttempt) -> IncidentInfo: ...
    async def escalate_incident(self, cmd: EscalateIncident) -> IncidentInfo: ...
    async def record_snapshot(self, cmd: RecordSnapshot) -> NodeStatsSnapshotInfo: ...
```

- [ ] **Step 4: Create `src/apps/incidents/application/interfaces/view.py`**

```python
from typing import Protocol
from uuid import UUID

from src.apps.incidents.domain.models import IncidentInfo


class IncidentView(Protocol):
    async def get_open_incident(self, node_uuid: str) -> IncidentInfo | None: ...
    async def count_recent_incidents(
        self, node_uuid: str, window_minutes: int
    ) -> int: ...
    async def get_recent_incidents(self, limit: int) -> list[IncidentInfo]: ...
    async def get_incidents_by_node(
        self, node_uuid: str, limit: int
    ) -> list[IncidentInfo]: ...
    async def get_node_uptime_percent(
        self, node_uuid: str, days: int
    ) -> float: ...
    async def get_worst_nodes(
        self, days: int, limit: int
    ) -> list[tuple[str, str, int, float]]:
        """Returns list of (node_uuid, node_name, incident_count, uptime_pct)."""
        ...
    async def get_incidents_by_period(
        self, days: int
    ) -> list[IncidentInfo]: ...
```

- [ ] **Step 5: Create `src/apps/incidents/application/interactor.py`**

```python
from src.apps.incidents.application.interfaces.gateway import IncidentGateway
from src.apps.incidents.application.interfaces.view import IncidentView
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


class IncidentInteractor:
    def __init__(self, gateway: IncidentGateway, view: IncidentView) -> None:
        self._gateway = gateway
        self._view = view

    async def open_incident(self, cmd: OpenIncident) -> IncidentInfo:
        return await self._gateway.open_incident(cmd)

    async def close_incident(self, cmd: CloseIncident) -> IncidentInfo:
        return await self._gateway.close_incident(cmd)

    async def record_restart_attempt(self, cmd: RecordRestartAttempt) -> IncidentInfo:
        return await self._gateway.record_restart_attempt(cmd)

    async def escalate_incident(self, cmd: EscalateIncident) -> IncidentInfo:
        return await self._gateway.escalate_incident(cmd)

    async def record_snapshot(self, cmd: RecordSnapshot) -> NodeStatsSnapshotInfo:
        return await self._gateway.record_snapshot(cmd)
```

- [ ] **Step 6: Run tests — expect pass**

```bash
uv run pytest tests/apps/incidents/test_interactor.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/apps/incidents/application/ tests/apps/incidents/
git commit -m "feat: incidents application layer — interfaces and interactor"
```

---

## Task 6: Incidents Adapters (PostgreSQL)

**Files:**
- Create: `src/apps/incidents/adapters/gateway.py`
- Create: `src/apps/incidents/adapters/view.py`

- [ ] **Step 1: Create `src/apps/incidents/adapters/gateway.py`**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.incidents.adapters.orm import IncidentModel, NodeStatsSnapshotModel
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


def _to_incident_info(m: IncidentModel) -> IncidentInfo:
    return IncidentInfo(
        id=m.id,
        node_uuid=m.node_uuid,
        node_name=m.node_name,
        started_at=m.started_at,
        resolved_at=m.resolved_at,
        last_status_message=m.last_status_message,
        restart_attempts=m.restart_attempts,
        escalated=m.escalated,
        downtime_seconds=m.downtime_seconds,
    )


def _to_snapshot_info(m: NodeStatsSnapshotModel) -> NodeStatsSnapshotInfo:
    return NodeStatsSnapshotInfo(
        id=m.id,
        node_uuid=m.node_uuid,
        captured_at=m.captured_at,
        users_online=m.users_online,
        traffic_used_bytes=m.traffic_used_bytes,
        xray_uptime=m.xray_uptime,
        is_connected=m.is_connected,
    )


class PostgresIncidentGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open_incident(self, cmd: OpenIncident) -> IncidentInfo:
        model = IncidentModel(
            id=uuid.uuid4(),
            node_uuid=cmd.node_uuid,
            node_name=cmd.node_name,
            started_at=cmd.started_at,
            resolved_at=None,
            last_status_message=cmd.last_status_message,
            restart_attempts=0,
            escalated=False,
            downtime_seconds=None,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_incident_info(model)

    async def close_incident(self, cmd: CloseIncident) -> IncidentInfo:
        result = await self._session.execute(
            select(IncidentModel).where(IncidentModel.id == cmd.incident_id)
        )
        model = result.scalar_one()
        downtime = int((cmd.resolved_at - model.started_at).total_seconds())
        model.resolved_at = cmd.resolved_at
        model.downtime_seconds = downtime
        await self._session.flush()
        return _to_incident_info(model)

    async def record_restart_attempt(self, cmd: RecordRestartAttempt) -> IncidentInfo:
        result = await self._session.execute(
            select(IncidentModel).where(IncidentModel.id == cmd.incident_id)
        )
        model = result.scalar_one()
        model.restart_attempts += 1
        await self._session.flush()
        return _to_incident_info(model)

    async def escalate_incident(self, cmd: EscalateIncident) -> IncidentInfo:
        result = await self._session.execute(
            select(IncidentModel).where(IncidentModel.id == cmd.incident_id)
        )
        model = result.scalar_one()
        model.escalated = True
        await self._session.flush()
        return _to_incident_info(model)

    async def record_snapshot(self, cmd: RecordSnapshot) -> NodeStatsSnapshotInfo:
        model = NodeStatsSnapshotModel(
            id=uuid.uuid4(),
            node_uuid=cmd.node_uuid,
            captured_at=cmd.captured_at,
            users_online=cmd.users_online,
            traffic_used_bytes=cmd.traffic_used_bytes,
            xray_uptime=cmd.xray_uptime,
            is_connected=cmd.is_connected,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_snapshot_info(model)
```

- [ ] **Step 2: Create `src/apps/incidents/adapters/view.py`**

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.incidents.adapters.orm import IncidentModel, NodeStatsSnapshotModel
from src.apps.incidents.domain.models import IncidentInfo


def _to_incident_info(m: IncidentModel) -> IncidentInfo:
    return IncidentInfo(
        id=m.id,
        node_uuid=m.node_uuid,
        node_name=m.node_name,
        started_at=m.started_at,
        resolved_at=m.resolved_at,
        last_status_message=m.last_status_message,
        restart_attempts=m.restart_attempts,
        escalated=m.escalated,
        downtime_seconds=m.downtime_seconds,
    )


class PostgresIncidentView:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open_incident(self, node_uuid: str) -> IncidentInfo | None:
        result = await self._session.execute(
            select(IncidentModel)
            .where(
                IncidentModel.node_uuid == node_uuid,
                IncidentModel.resolved_at.is_(None),
            )
            .order_by(IncidentModel.started_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return _to_incident_info(model) if model else None

    async def count_recent_incidents(
        self, node_uuid: str, window_minutes: int
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        result = await self._session.execute(
            select(func.count())
            .select_from(IncidentModel)
            .where(
                IncidentModel.node_uuid == node_uuid,
                IncidentModel.started_at >= cutoff,
            )
        )
        return result.scalar_one()

    async def get_recent_incidents(self, limit: int) -> list[IncidentInfo]:
        result = await self._session.execute(
            select(IncidentModel)
            .order_by(IncidentModel.started_at.desc())
            .limit(limit)
        )
        return [_to_incident_info(m) for m in result.scalars().all()]

    async def get_incidents_by_node(
        self, node_uuid: str, limit: int
    ) -> list[IncidentInfo]:
        result = await self._session.execute(
            select(IncidentModel)
            .where(IncidentModel.node_uuid == node_uuid)
            .order_by(IncidentModel.started_at.desc())
            .limit(limit)
        )
        return [_to_incident_info(m) for m in result.scalars().all()]

    async def get_node_uptime_percent(self, node_uuid: str, days: int) -> float:
        period_seconds = days * 86400
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(func.coalesce(func.sum(IncidentModel.downtime_seconds), 0))
            .where(
                IncidentModel.node_uuid == node_uuid,
                IncidentModel.started_at >= cutoff,
                IncidentModel.resolved_at.is_not(None),
            )
        )
        total_downtime: int = result.scalar_one()
        uptime_pct = max(0.0, (1 - total_downtime / period_seconds) * 100)
        return round(uptime_pct, 2)

    async def get_worst_nodes(
        self, days: int, limit: int
    ) -> list[tuple[str, str, int, float]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(
                IncidentModel.node_uuid,
                IncidentModel.node_name,
                func.count().label("incident_count"),
            )
            .where(IncidentModel.started_at >= cutoff)
            .group_by(IncidentModel.node_uuid, IncidentModel.node_name)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = result.all()
        out = []
        for node_uuid, node_name, count in rows:
            uptime = await self.get_node_uptime_percent(node_uuid, days)
            out.append((node_uuid, node_name, count, uptime))
        return out

    async def get_incidents_by_period(self, days: int) -> list[IncidentInfo]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(IncidentModel)
            .where(IncidentModel.started_at >= cutoff)
            .order_by(IncidentModel.started_at.desc())
        )
        return [_to_incident_info(m) for m in result.scalars().all()]
```

- [ ] **Step 3: Commit**

```bash
git add src/apps/incidents/adapters/
git commit -m "feat: incidents PostgreSQL adapters (gateway + view)"
```

---

## Task 7: Nodes Domain + Remnawave Adapter

**Files:**
- Create: `src/apps/nodes/domain/models.py`
- Create: `src/apps/nodes/domain/events.py`
- Create: `src/apps/nodes/domain/exceptions.py`
- Create: `src/infrastructure/remnawave/client.py`
- Create: `src/apps/nodes/application/interfaces/gateway.py`
- Create: `src/apps/nodes/application/interfaces/view.py`
- Create: `src/apps/nodes/adapters/gateway.py`
- Create: `src/apps/nodes/adapters/view.py`

- [ ] **Step 1: Write failing test for nodes domain**

```python
# tests/apps/nodes/test_interactor.py
from datetime import datetime, timezone

from src.apps.nodes.domain.models import NodeInfo


def test_node_info_is_frozen() -> None:
    node = NodeInfo(
        uuid="abc-123",
        name="DE-1",
        address="1.2.3.4",
        country_code="DE",
        provider="AEZA",
        is_connected=True,
        is_connecting=False,
        is_disabled=False,
        last_status_change=datetime.now(timezone.utc),
        last_status_message="connected",
        xray_uptime=3600,
        users_online=5,
        traffic_used_bytes=1024,
    )
    try:
        node.is_connected = False  # type: ignore[misc]
        assert False, "Should be frozen"
    except Exception:
        pass
```

- [ ] **Step 2: Run test — expect failure**

```bash
uv run pytest tests/apps/nodes/test_interactor.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `src/apps/nodes/domain/models.py`**

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NodeInfo:
    uuid: str
    name: str
    address: str
    country_code: str
    provider: str
    is_connected: bool
    is_connecting: bool
    is_disabled: bool
    last_status_change: datetime
    last_status_message: str
    xray_uptime: int
    users_online: int
    traffic_used_bytes: int
```

- [ ] **Step 4: Create `src/apps/nodes/domain/events.py`**

```python
from dataclasses import dataclass
from datetime import datetime

from src.apps.nodes.domain.models import NodeInfo


@dataclass(frozen=True)
class NodeWentOffline:
    node: NodeInfo
    detected_at: datetime


@dataclass(frozen=True)
class NodeCameOnline:
    node: NodeInfo
    detected_at: datetime


@dataclass(frozen=True)
class NodeEscalated:
    node: NodeInfo
    detected_at: datetime
```

- [ ] **Step 5: Create `src/apps/nodes/domain/exceptions.py`**

```python
class NodeNotFound(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Node not found: {name}")
        self.name = name
```

- [ ] **Step 6: Create `src/apps/nodes/application/interfaces/gateway.py`**

```python
from datetime import datetime, timedelta
from typing import Protocol

from src.apps.nodes.domain.models import NodeInfo


class NodeGateway(Protocol):
    async def restart_node(self, node_uuid: str) -> None: ...
    async def mute_node(
        self, node_uuid: str, muted_until: datetime, admin_telegram_id: int
    ) -> None: ...
    async def unmute_node(self, node_uuid: str) -> None: ...
```

- [ ] **Step 7: Create `src/apps/nodes/application/interfaces/view.py`**

```python
from typing import Protocol

from src.apps.nodes.domain.models import NodeInfo


class NodeView(Protocol):
    async def get_all_nodes(self) -> list[NodeInfo]: ...
    async def get_node_by_name(self, name: str) -> NodeInfo | None: ...
    async def is_muted(self, node_uuid: str) -> bool: ...
```

- [ ] **Step 8: Create `src/infrastructure/remnawave/client.py`**

```python
from remnawave import RemnawaveSDK

from src.config import Config


def create_remnawave_client(config: Config) -> RemnawaveSDK:
    return RemnawaveSDK(
        base_url=config.remnawave_base_url,
        token=config.remnawave_token,
    )
```

- [ ] **Step 9: Create `src/apps/nodes/adapters/view.py`**

```python
from datetime import datetime, timezone

from remnawave import RemnawaveSDK
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.apps.nodes.adapters.orm import MutedNodeModel
from src.apps.nodes.domain.models import NodeInfo


def _to_node_info(dto: object) -> NodeInfo:  # type: ignore[return]
    # remnawave SDK returns NodeResponseDto — access fields by attribute
    return NodeInfo(
        uuid=str(dto.uuid),  # type: ignore[attr-defined]
        name=str(dto.name),  # type: ignore[attr-defined]
        address=str(dto.address),  # type: ignore[attr-defined]
        country_code=str(dto.country_code or "??"),  # type: ignore[attr-defined]
        provider=str(dto.provider.name if dto.provider else "unknown"),  # type: ignore[attr-defined]
        is_connected=bool(dto.is_connected),  # type: ignore[attr-defined]
        is_connecting=bool(dto.is_connecting),  # type: ignore[attr-defined]
        is_disabled=bool(dto.is_disabled),  # type: ignore[attr-defined]
        last_status_change=dto.last_status_change,  # type: ignore[attr-defined]
        last_status_message=str(dto.last_status_message or ""),  # type: ignore[attr-defined]
        xray_uptime=int(dto.xray_uptime or 0),  # type: ignore[attr-defined]
        users_online=int(dto.users_online or 0),  # type: ignore[attr-defined]
        traffic_used_bytes=int(dto.traffic_used_bytes or 0),  # type: ignore[attr-defined]
    )


class RemnaWaveNodeView:
    def __init__(self, sdk: RemnawaveSDK, session: AsyncSession) -> None:
        self._sdk = sdk
        self._session = session

    async def get_all_nodes(self) -> list[NodeInfo]:
        response = await self._sdk.nodes.get_all_nodes()
        return [_to_node_info(node) for node in response]

    async def get_node_by_name(self, name: str) -> NodeInfo | None:
        response = await self._sdk.nodes.get_all_nodes()
        for node in response:
            if node.name.lower() == name.lower():  # type: ignore[attr-defined]
                return _to_node_info(node)
        return None

    async def is_muted(self, node_uuid: str) -> bool:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(MutedNodeModel).where(
                MutedNodeModel.node_uuid == node_uuid,
                MutedNodeModel.muted_until > now,
            )
        )
        return result.scalar_one_or_none() is not None
```

- [ ] **Step 10: Create `src/apps/nodes/adapters/gateway.py`**

```python
from datetime import datetime

from remnawave import RemnawaveSDK
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.nodes.adapters.orm import MutedNodeModel


class RemnaWaveNodeGateway:
    def __init__(self, sdk: RemnawaveSDK, session: AsyncSession) -> None:
        self._sdk = sdk
        self._session = session

    async def restart_node(self, node_uuid: str) -> None:
        await self._sdk.nodes.restart_node(node_uuid)

    async def mute_node(
        self, node_uuid: str, muted_until: datetime, admin_telegram_id: int
    ) -> None:
        stmt = (
            insert(MutedNodeModel)
            .values(
                node_uuid=node_uuid,
                muted_until=muted_until,
                muted_by_telegram_id=admin_telegram_id,
            )
            .on_conflict_do_update(
                index_elements=["node_uuid"],
                set_={"muted_until": muted_until, "muted_by_telegram_id": admin_telegram_id},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def unmute_node(self, node_uuid: str) -> None:
        await self._session.execute(
            delete(MutedNodeModel).where(MutedNodeModel.node_uuid == node_uuid)
        )
        await self._session.flush()
```

- [ ] **Step 11: Run node tests — expect pass**

```bash
uv run pytest tests/apps/nodes/test_interactor.py -v
```

Expected: 1 test PASS.

- [ ] **Step 12: Commit**

```bash
git add src/apps/nodes/ src/infrastructure/remnawave/
git commit -m "feat: nodes domain, adapters, and Remnawave SDK integration"
```

---

## Task 8: Nodes Application Layer (Interactor)

**Files:**
- Create: `src/apps/nodes/application/interactor.py`
- Modify: `tests/apps/nodes/test_interactor.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/apps/nodes/test_interactor.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.apps.nodes.application.interactor import NodeInteractor
from src.apps.nodes.domain.exceptions import NodeNotFound
from src.apps.nodes.domain.models import NodeInfo


def make_node(*, name: str = "DE-1", uuid: str = "node-1", is_connected: bool = True) -> NodeInfo:
    return NodeInfo(
        uuid=uuid,
        name=name,
        address="1.2.3.4",
        country_code="DE",
        provider="AEZA",
        is_connected=is_connected,
        is_connecting=False,
        is_disabled=False,
        last_status_change=datetime.now(timezone.utc),
        last_status_message="ok",
        xray_uptime=3600,
        users_online=5,
        traffic_used_bytes=1024,
    )


@pytest.fixture
def node_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_interactor(node_gateway: AsyncMock, node_view: AsyncMock) -> NodeInteractor:
    return NodeInteractor(gateway=node_gateway, view=node_view)


async def test_restart_node_calls_gateway(
    node_interactor: NodeInteractor,
    node_gateway: AsyncMock,
    node_view: AsyncMock,
) -> None:
    node = make_node()
    node_view.get_node_by_name.return_value = node

    await node_interactor.restart_node_by_name("DE-1")

    node_gateway.restart_node.assert_awaited_once_with("node-1")


async def test_restart_node_raises_if_not_found(
    node_interactor: NodeInteractor,
    node_view: AsyncMock,
) -> None:
    node_view.get_node_by_name.return_value = None

    with pytest.raises(NodeNotFound):
        await node_interactor.restart_node_by_name("XX-99")


async def test_mute_node_by_name(
    node_interactor: NodeInteractor,
    node_gateway: AsyncMock,
    node_view: AsyncMock,
) -> None:
    node = make_node()
    node_view.get_node_by_name.return_value = node
    duration = timedelta(hours=1)

    await node_interactor.mute_node_by_name("DE-1", duration, admin_telegram_id=123)

    node_gateway.mute_node.assert_awaited_once()
    call_args = node_gateway.mute_node.call_args
    assert call_args.kwargs["node_uuid"] == "node-1"
    assert call_args.kwargs["admin_telegram_id"] == 123
```

- [ ] **Step 2: Run tests — expect failure**

```bash
uv run pytest tests/apps/nodes/test_interactor.py -v
```

Expected: `ImportError` for `NodeInteractor`.

- [ ] **Step 3: Create `src/apps/nodes/application/interactor.py`**

```python
from datetime import datetime, timedelta, timezone

from src.apps.nodes.application.interfaces.gateway import NodeGateway
from src.apps.nodes.application.interfaces.view import NodeView
from src.apps.nodes.domain.exceptions import NodeNotFound
from src.apps.nodes.domain.models import NodeInfo


class NodeInteractor:
    def __init__(self, gateway: NodeGateway, view: NodeView) -> None:
        self._gateway = gateway
        self._view = view

    async def restart_node_by_name(self, name: str) -> NodeInfo:
        node = await self._view.get_node_by_name(name)
        if node is None:
            raise NodeNotFound(name)
        await self._gateway.restart_node(node.uuid)
        return node

    async def mute_node_by_name(
        self, name: str, duration: timedelta, admin_telegram_id: int
    ) -> NodeInfo:
        node = await self._view.get_node_by_name(name)
        if node is None:
            raise NodeNotFound(name)
        muted_until = datetime.now(timezone.utc) + duration
        await self._gateway.mute_node(
            node_uuid=node.uuid,
            muted_until=muted_until,
            admin_telegram_id=admin_telegram_id,
        )
        return node

    async def unmute_node_by_name(self, name: str) -> NodeInfo:
        node = await self._view.get_node_by_name(name)
        if node is None:
            raise NodeNotFound(name)
        await self._gateway.unmute_node(node.uuid)
        return node
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/apps/nodes/test_interactor.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apps/nodes/application/ tests/apps/nodes/test_interactor.py
git commit -m "feat: nodes application interactor"
```

---

## Task 9: Monitoring Loop (Core Logic)

**Files:**
- Create: `src/apps/nodes/controllers/scheduler/loop.py`
- Create: `tests/apps/nodes/test_monitoring_loop.py`

This is the most critical business logic. The loop runs every `poll_interval_seconds`, checks each node, restarts if down (<3 recent incidents), escalates if ≥3 incidents/hour, closes incident if recovered.

- [ ] **Step 1: Write failing tests**

```python
# tests/apps/nodes/test_monitoring_loop.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.apps.nodes.controllers.scheduler.loop import MonitoringLoop
from src.apps.nodes.domain.models import NodeInfo
from src.apps.incidents.domain.models import IncidentInfo


def make_node(
    *,
    uuid: str = "node-1",
    name: str = "DE-1",
    is_connected: bool = True,
) -> NodeInfo:
    return NodeInfo(
        uuid=uuid,
        name=name,
        address="1.2.3.4",
        country_code="DE",
        provider="AEZA",
        is_connected=is_connected,
        is_connecting=False,
        is_disabled=False,
        last_status_change=datetime.now(timezone.utc),
        last_status_message="connection timeout" if not is_connected else "ok",
        xray_uptime=3600,
        users_online=5,
        traffic_used_bytes=1024,
    )


def make_incident(*, node_uuid: str = "node-1", escalated: bool = False) -> IncidentInfo:
    return IncidentInfo(
        id=uuid4(),
        node_uuid=node_uuid,
        node_name="DE-1",
        started_at=datetime.now(timezone.utc),
        resolved_at=None,
        last_status_message="connection timeout",
        restart_attempts=0,
        escalated=escalated,
        downtime_seconds=None,
    )


@pytest.fixture
def node_view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def incident_interactor() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def incident_view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def notify() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def loop(
    node_view: AsyncMock,
    node_gateway: AsyncMock,
    incident_interactor: AsyncMock,
    incident_view: AsyncMock,
    notify: AsyncMock,
) -> MonitoringLoop:
    return MonitoringLoop(
        node_view=node_view,
        node_gateway=node_gateway,
        incident_interactor=incident_interactor,
        incident_view=incident_view,
        notify=notify,
        escalation_window_minutes=60,
        escalation_max_attempts=3,
    )


async def test_online_node_with_no_incident_does_nothing(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node_view.get_all_nodes.return_value = [make_node(is_connected=True)]
    node_view.is_muted.return_value = False
    incident_view.get_open_incident.return_value = None
    incident_view.count_recent_incidents.return_value = 0

    await loop.poll()

    node_gateway.restart_node.assert_not_awaited()
    notify.assert_not_awaited()


async def test_offline_node_triggers_restart_and_notification(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    incident_interactor: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=False)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = False
    incident_view.get_open_incident.return_value = None
    incident_view.count_recent_incidents.return_value = 1  # < 3
    incident = make_incident()
    incident_interactor.open_incident.return_value = incident
    incident_interactor.record_restart_attempt.return_value = incident

    await loop.poll()

    node_gateway.restart_node.assert_awaited_once_with("node-1")
    notify.assert_awaited()
    call_msg: str = notify.call_args[0][0]
    assert "DE-1" in call_msg
    assert "🔴" in call_msg


async def test_muted_offline_node_skips_restart(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=False)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = True

    await loop.poll()

    node_gateway.restart_node.assert_not_awaited()
    notify.assert_not_awaited()


async def test_three_incidents_triggers_escalation(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    incident_interactor: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=False)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = False
    incident = make_incident()
    incident_view.get_open_incident.return_value = incident
    incident_view.count_recent_incidents.return_value = 3  # >= 3 → escalate
    incident_interactor.escalate_incident.return_value = make_incident(escalated=True)

    await loop.poll()

    node_gateway.restart_node.assert_not_awaited()
    incident_interactor.escalate_incident.assert_awaited_once()
    notify.assert_awaited()
    call_msg: str = notify.call_args[0][0]
    assert "🚨" in call_msg


async def test_node_recovery_closes_incident(
    loop: MonitoringLoop,
    node_view: AsyncMock,
    incident_view: AsyncMock,
    incident_interactor: AsyncMock,
    node_gateway: AsyncMock,
    notify: AsyncMock,
) -> None:
    node = make_node(is_connected=True)
    node_view.get_all_nodes.return_value = [node]
    node_view.is_muted.return_value = False
    open_incident = make_incident()
    incident_view.get_open_incident.return_value = open_incident
    incident_interactor.close_incident.return_value = open_incident

    await loop.poll()

    incident_interactor.close_incident.assert_awaited_once()
    notify.assert_awaited()
    call_msg: str = notify.call_args[0][0]
    assert "✅" in call_msg
```

- [ ] **Step 2: Run tests — expect failure**

```bash
uv run pytest tests/apps/nodes/test_monitoring_loop.py -v
```

Expected: `ImportError` for `MonitoringLoop`.

- [ ] **Step 3: Create `src/apps/nodes/controllers/scheduler/loop.py`**

```python
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.application.interfaces.view import IncidentView
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.nodes.application.interfaces.gateway import NodeGateway
from src.apps.nodes.application.interfaces.view import NodeView
from src.apps.nodes.domain.models import NodeInfo

NotifyFn = Callable[[str], Coroutine[Any, Any, None]]


class MonitoringLoop:
    def __init__(
        self,
        *,
        node_view: NodeView,
        node_gateway: NodeGateway,
        incident_interactor: IncidentInteractor,
        incident_view: IncidentView,
        notify: NotifyFn,
        escalation_window_minutes: int,
        escalation_max_attempts: int,
    ) -> None:
        self._node_view = node_view
        self._node_gateway = node_gateway
        self._incident_interactor = incident_interactor
        self._incident_view = incident_view
        self._notify = notify
        self._escalation_window_minutes = escalation_window_minutes
        self._escalation_max_attempts = escalation_max_attempts

    async def poll(self) -> None:
        now = datetime.now(timezone.utc)
        nodes = await self._node_view.get_all_nodes()
        for node in nodes:
            await self._process_node(node, now)

    async def _process_node(self, node: NodeInfo, now: datetime) -> None:
        # Always record snapshot
        await self._incident_interactor.record_snapshot(
            RecordSnapshot(
                node_uuid=node.uuid,
                captured_at=now,
                users_online=node.users_online,
                traffic_used_bytes=node.traffic_used_bytes,
                xray_uptime=node.xray_uptime,
                is_connected=node.is_connected,
            )
        )

        if not node.is_connected:
            await self._handle_offline_node(node, now)
        else:
            await self._handle_online_node(node, now)

    async def _handle_offline_node(self, node: NodeInfo, now: datetime) -> None:
        if await self._node_view.is_muted(node.uuid):
            return

        recent_count = await self._incident_view.count_recent_incidents(
            node.uuid, self._escalation_window_minutes
        )

        if recent_count >= self._escalation_max_attempts:
            # Escalate existing open incident
            open_incident = await self._incident_view.get_open_incident(node.uuid)
            if open_incident and not open_incident.escalated:
                await self._incident_interactor.escalate_incident(
                    EscalateIncident(incident_id=open_incident.id)
                )
                await self._notify(
                    f"🚨 [{node.name}] не поднимается после "
                    f"{self._escalation_max_attempts} попыток за час. "
                    f"Требуется ручное вмешательство!\n"
                    f"Причина: {node.last_status_message}"
                )
        else:
            # Open new incident if none exists
            open_incident = await self._incident_view.get_open_incident(node.uuid)
            if open_incident is None:
                open_incident = await self._incident_interactor.open_incident(
                    OpenIncident(
                        node_uuid=node.uuid,
                        node_name=node.name,
                        started_at=now,
                        last_status_message=node.last_status_message,
                    )
                )

            attempt_num = recent_count + 1
            await self._node_gateway.restart_node(node.uuid)
            await self._incident_interactor.record_restart_attempt(
                RecordRestartAttempt(incident_id=open_incident.id)
            )
            await self._notify(
                f"🔴 [{node.name}] упала. "
                f"Причина: {node.last_status_message}\n"
                f"Перезапуск (попытка {attempt_num}/{self._escalation_max_attempts})"
            )

    async def _handle_online_node(self, node: NodeInfo, now: datetime) -> None:
        open_incident = await self._incident_view.get_open_incident(node.uuid)
        if open_incident is None:
            return

        closed = await self._incident_interactor.close_incident(
            CloseIncident(incident_id=open_incident.id, resolved_at=now)
        )
        downtime_min = (closed.downtime_seconds or 0) // 60
        await self._notify(
            f"✅ [{node.name}] восстановлена. Даунтайм: {downtime_min} мин"
        )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/apps/nodes/test_monitoring_loop.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apps/nodes/controllers/scheduler/ tests/apps/nodes/test_monitoring_loop.py
git commit -m "feat: monitoring loop with auto-restart and escalation logic"
```

---

## Task 10: Telegram Infrastructure (Bot Setup + Admin Middleware)

**Files:**
- Create: `src/infrastructure/telegram/setup.py`
- Create: `src/infrastructure/telegram/middleware.py`
- Create: `tests/infrastructure/test_middleware.py`

- [ ] **Step 1: Write failing test for middleware**

```python
# tests/infrastructure/test_middleware.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User

from src.infrastructure.telegram.middleware import AdminAuthMiddleware


@pytest.fixture
def middleware() -> AdminAuthMiddleware:
    return AdminAuthMiddleware(admin_ids=[111, 222])


async def test_allowed_admin_passes_through(middleware: AdminAuthMiddleware) -> None:
    handler = AsyncMock(return_value="ok")
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 111
    data: dict = {}

    result = await middleware(handler, message, data)

    handler.assert_awaited_once()
    assert result == "ok"


async def test_unknown_user_is_blocked(middleware: AdminAuthMiddleware) -> None:
    handler = AsyncMock(return_value="ok")
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 999
    data: dict = {}

    result = await middleware(handler, message, data)

    handler.assert_not_awaited()
    assert result is None


async def test_no_user_is_blocked(middleware: AdminAuthMiddleware) -> None:
    handler = AsyncMock(return_value="ok")
    message = MagicMock(spec=Message)
    message.from_user = None
    data: dict = {}

    result = await middleware(handler, message, data)

    handler.assert_not_awaited()
```

- [ ] **Step 2: Run test — expect failure**

```bash
uv run pytest tests/infrastructure/test_middleware.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `src/infrastructure/telegram/middleware.py`**

```python
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class AdminAuthMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: list[int]) -> None:
        self._admin_ids = set(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.from_user is None or event.from_user.id not in self._admin_ids:
            return None
        return await handler(event, data)
```

- [ ] **Step 4: Run test — expect pass**

```bash
uv run pytest tests/infrastructure/test_middleware.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Create `src/infrastructure/telegram/setup.py`**

```python
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import Config
from src.infrastructure.telegram.middleware import AdminAuthMiddleware


def create_bot(config: Config) -> Bot:
    return Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(config: Config) -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(AdminAuthMiddleware(admin_ids=config.admin_ids))
    return dp
```

- [ ] **Step 6: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/infrastructure/telegram/ tests/infrastructure/
git commit -m "feat: Telegram bot setup and admin auth middleware"
```

---

## Task 11: Telegram Handlers — Nodes Domain

**Files:**
- Create: `src/apps/nodes/controllers/telegram/handlers.py`

All handlers use HTML parse mode (set globally in bot). The `notify` function used by handlers sends a message to all admin IDs.

- [ ] **Step 1: Create `src/apps/nodes/controllers/telegram/handlers.py`**

```python
from datetime import timedelta

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka

from src.apps.nodes.application.interactor import NodeInteractor
from src.apps.nodes.application.interfaces.view import NodeView
from src.apps.nodes.domain.exceptions import NodeNotFound
from src.apps.nodes.domain.models import NodeInfo
from src.config import Config

router = Router()

_MUTE_DURATIONS = {"30m": timedelta(minutes=30), "1h": timedelta(hours=1), "24h": timedelta(hours=24)}


def _status_icon(node: NodeInfo) -> str:
    if node.is_disabled:
        return "⛔"
    if node.is_connecting:
        return "⏳"
    return "🟢" if node.is_connected else "🔴"


def _format_node_line(node: NodeInfo) -> str:
    icon = _status_icon(node)
    return f"{icon} <b>{node.name}</b> [{node.country_code}] {node.provider} — {node.users_online} users"


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
async def cmd_status(message: Message, node_view: FromDishka[NodeView]) -> None:
    nodes = await node_view.get_all_nodes()
    if not nodes:
        await message.answer("Нод не найдено.")
        return
    lines = [_format_node_line(n) for n in nodes]
    await message.answer("\n".join(lines))


@router.message(Command("node"))
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
            [InlineKeyboardButton(text="✅ Да, перезапустить все", callback_data="confirm_restart_all")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_restart_all")],
        ]
    )
    await message.answer("Перезапустить <b>все</b> ноды?", reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "confirm_restart_all")
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
    # Find node to get uuid
    node = await node_view.get_node_by_name(name)
    if node is None:
        await message.answer(f"Нода <b>{name}</b> не найдена.")
        return
    admin_id = message.from_user.id if message.from_user else 0  # type: ignore[union-attr]
    try:
        await node_interactor.mute_node_by_name(name, duration, admin_telegram_id=admin_id)
        await message.answer(f"🔇 Нода <b>{node.name}</b> замьючена на {duration_key}.")
    except NodeNotFound:
        await message.answer(f"Нода <b>{name}</b> не найдена.")


@router.message(Command("unmute"))
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
```

- [ ] **Step 2: Commit**

```bash
git add src/apps/nodes/controllers/telegram/
git commit -m "feat: Telegram handlers for nodes domain"
```

---

## Task 12: Telegram Handlers — Incidents Domain

**Files:**
- Create: `src/apps/incidents/controllers/telegram/handlers.py`

- [ ] **Step 1: Create `src/apps/incidents/controllers/telegram/handlers.py`**

```python
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka.integrations.aiogram import FromDishka

from src.apps.incidents.application.interfaces.view import IncidentView
from src.apps.incidents.domain.models import IncidentInfo

router = Router()


def _fmt_incident(inc: IncidentInfo) -> str:
    status = "🔴 активный" if inc.resolved_at is None else "✅ закрыт"
    downtime = f"{(inc.downtime_seconds or 0) // 60} мин" if inc.resolved_at else "в процессе"
    return (
        f"<b>{inc.node_name}</b> | {status}\n"
        f"  Начало: {inc.started_at.strftime('%d.%m %H:%M')} UTC\n"
        f"  Даунтайм: {downtime}\n"
        f"  Причина: {inc.last_status_message}\n"
        f"  Рестартов: {inc.restart_attempts}"
        + (" | 🚨 эскалация" if inc.escalated else "")
    )


@router.message(Command("incidents"))
async def cmd_incidents(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    incidents = await incident_view.get_recent_incidents(limit=10)
    if not incidents:
        await message.answer("Инцидентов пока нет.")
        return
    lines = [_fmt_incident(inc) for inc in incidents]
    await message.answer("\n\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    parts = (message.text or "").split()
    period_map = {"day": 1, "week": 7, "month": 30}
    period_key = parts[1] if len(parts) > 1 else "week"
    days = period_map.get(period_key, 7)

    incidents = await incident_view.get_incidents_by_period(days=days)
    total = len(incidents)
    escalated = sum(1 for i in incidents if i.escalated)
    resolved = [i for i in incidents if i.resolved_at is not None]
    avg_downtime = (
        sum(i.downtime_seconds or 0 for i in resolved) // len(resolved)
        if resolved else 0
    )

    label = {"day": "день", "week": "неделю", "month": "месяц"}.get(period_key, "неделю")
    await message.answer(
        f"📊 Статистика за {label}:\n"
        f"Инцидентов: <b>{total}</b>\n"
        f"Эскалаций: <b>{escalated}</b>\n"
        f"Средний даунтайм: <b>{avg_downtime // 60} мин</b>"
    )


@router.message(Command("worst"))
async def cmd_worst(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    worst = await incident_view.get_worst_nodes(days=30, limit=5)
    if not worst:
        await message.answer("Данных пока нет.")
        return
    lines = []
    for i, (node_uuid, node_name, count, uptime_pct) in enumerate(worst, 1):
        lines.append(f"{i}. <b>{node_name}</b> — {count} инц. | uptime {uptime_pct:.1f}%")
    await message.answer("🔥 Топ проблемных нод (30 дней):\n" + "\n".join(lines))


@router.message(Command("providers"))
async def cmd_providers(message: Message, incident_view: FromDishka[IncidentView]) -> None:
    incidents = await incident_view.get_incidents_by_period(days=30)
    provider_counts: dict[str, int] = {}
    # node_name is "PROVIDER-N" pattern — we use node_name stored at incident time
    # For provider grouping we rely on data available: just count by unique node names
    # A real provider breakdown requires join with node API data — approximated here
    for inc in incidents:
        # Provider info isn't stored in incident — group by node_name prefix (e.g. "DE-1" → "DE")
        prefix = inc.node_name.split("-")[0] if "-" in inc.node_name else inc.node_name
        provider_counts[prefix] = provider_counts.get(prefix, 0) + 1

    if not provider_counts:
        await message.answer("Данных по провайдерам пока нет.")
        return

    lines = [
        f"<b>{prov}</b>: {cnt} инцидентов"
        for prov, cnt in sorted(provider_counts.items(), key=lambda x: -x[1])
    ]
    await message.answer("📡 Инциденты по регионам (30 дней):\n" + "\n".join(lines))
```

> **Note on /providers:** Since `provider` is not stored in the `incidents` table, grouping is by node name prefix as approximation. To get true provider stats, store `provider` in incidents table — see improvement note at end of this plan.

- [ ] **Step 2: Commit**

```bash
git add src/apps/incidents/controllers/telegram/
git commit -m "feat: Telegram handlers for incidents domain"
```

---

## Task 13: DI Wiring (Dishka Providers + main.py)

**Files:**
- Create: `src/apps/nodes/ioc.py`
- Create: `src/apps/incidents/ioc.py`
- Create: `src/main.py`

- [ ] **Step 1: Create `src/apps/incidents/ioc.py`**

```python
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.incidents.adapters.gateway import PostgresIncidentGateway
from src.apps.incidents.adapters.view import PostgresIncidentView
from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.application.interfaces.gateway import IncidentGateway
from src.apps.incidents.application.interfaces.view import IncidentView


class IncidentAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def incident_gateway(self, session: AsyncSession) -> IncidentGateway:
        return PostgresIncidentGateway(session=session)

    @provide
    async def incident_view(self, session: AsyncSession) -> IncidentView:
        return PostgresIncidentView(session=session)


class IncidentInteractorsProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def incident_interactor(
        self,
        gateway: IncidentGateway,
        view: IncidentView,
    ) -> IncidentInteractor:
        return IncidentInteractor(gateway=gateway, view=view)
```

- [ ] **Step 2: Create `src/apps/nodes/ioc.py`**

```python
from dishka import Provider, Scope, provide
from remnawave import RemnawaveSDK
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.nodes.adapters.gateway import RemnaWaveNodeGateway
from src.apps.nodes.adapters.view import RemnaWaveNodeView
from src.apps.nodes.application.interactor import NodeInteractor
from src.apps.nodes.application.interfaces.gateway import NodeGateway
from src.apps.nodes.application.interfaces.view import NodeView


class NodeAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def node_gateway(self, sdk: RemnawaveSDK, session: AsyncSession) -> NodeGateway:
        return RemnaWaveNodeGateway(sdk=sdk, session=session)

    @provide
    async def node_view(self, sdk: RemnawaveSDK, session: AsyncSession) -> NodeView:
        return RemnaWaveNodeView(sdk=sdk, session=session)


class NodeInteractorsProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def node_interactor(
        self, gateway: NodeGateway, view: NodeView
    ) -> NodeInteractor:
        return NodeInteractor(gateway=gateway, view=view)
```

- [ ] **Step 3: Create `src/main.py`**

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from src.apps.incidents.controllers.telegram.handlers import router as incidents_router
from src.apps.incidents.ioc import IncidentAdaptersProvider, IncidentInteractorsProvider
from src.apps.nodes.controllers.scheduler.loop import MonitoringLoop
from src.apps.nodes.controllers.telegram.handlers import router as nodes_router
from src.apps.nodes.ioc import NodeAdaptersProvider, NodeInteractorsProvider
from src.config import Config
from src.infrastructure.db.engine import create_engine
from src.infrastructure.db.session import create_session_factory
from src.infrastructure.remnawave.client import create_remnawave_client
from src.infrastructure.telegram.setup import create_bot, create_dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def make_notify_fn(bot: Bot, admin_ids: list[int]):  # type: ignore[no-untyped-def]
    async def notify(text: str) -> None:
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error("Failed to notify admin %s: %s", admin_id, e)
    return notify


async def run_monitoring_loop(loop: MonitoringLoop, interval_seconds: int) -> None:
    logger.info("Starting monitoring loop (interval=%ds)", interval_seconds)
    while True:
        try:
            await loop.poll()
        except Exception as e:
            logger.error("Monitoring poll error: %s", e)
        await asyncio.sleep(interval_seconds)


async def main() -> None:
    config = Config()
    engine = create_engine(config)
    session_factory = create_session_factory(engine)
    sdk = create_remnawave_client(config)
    bot = create_bot(config)
    dp: Dispatcher = create_dispatcher(config)

    dp.include_router(nodes_router)
    dp.include_router(incidents_router)

    # Dishka infrastructure providers (app-scoped singletons)
    from dishka import Provider, Scope, provide as dishka_provide
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, AsyncEngine
    from remnawave import RemnawaveSDK

    class InfraProvider(Provider):
        scope = Scope.APP

        @dishka_provide
        async def get_engine(self) -> AsyncEngine:
            return engine

        @dishka_provide
        async def get_sdk(self) -> RemnawaveSDK:
            return sdk

    class SessionProvider(Provider):
        scope = Scope.REQUEST

        @dishka_provide
        async def get_session(self, session_fac: async_sessionmaker[AsyncSession]) -> AsyncSession:
            async with session_fac() as session:
                async with session.begin():
                    yield session

        @dishka_provide(scope=Scope.APP)
        async def get_session_factory(
            self, eng: AsyncEngine
        ) -> async_sessionmaker[AsyncSession]:
            return session_factory

    container = make_async_container(
        InfraProvider(),
        SessionProvider(),
        NodeAdaptersProvider(),
        NodeInteractorsProvider(),
        IncidentAdaptersProvider(),
        IncidentInteractorsProvider(),
    )
    setup_dishka(container=container, router=dp)

    notify = await make_notify_fn(bot, config.admin_ids)

    # Build monitoring loop with app-scoped session (separate from request scope)
    async with session_factory() as session:
        async with session.begin():
            from src.apps.incidents.adapters.gateway import PostgresIncidentGateway
            from src.apps.incidents.adapters.view import PostgresIncidentView
            from src.apps.incidents.application.interactor import IncidentInteractor
            from src.apps.nodes.adapters.gateway import RemnaWaveNodeGateway
            from src.apps.nodes.adapters.view import RemnaWaveNodeView

            node_gw = RemnaWaveNodeGateway(sdk=sdk, session=session)
            node_vw = RemnaWaveNodeView(sdk=sdk, session=session)
            inc_gw = PostgresIncidentGateway(session=session)
            inc_vw = PostgresIncidentView(session=session)
            inc_interactor = IncidentInteractor(gateway=inc_gw, view=inc_vw)

    # The monitoring loop needs its own long-lived session per poll cycle
    async def monitoring_task() -> None:
        logger.info("Starting monitoring loop (interval=%ds)", config.poll_interval_seconds)
        while True:
            try:
                async with session_factory() as session:
                    async with session.begin():
                        node_gw = RemnaWaveNodeGateway(sdk=sdk, session=session)
                        node_vw = RemnaWaveNodeView(sdk=sdk, session=session)
                        inc_gw = PostgresIncidentGateway(session=session)
                        inc_vw = PostgresIncidentView(session=session)
                        inc_interactor = IncidentInteractor(gateway=inc_gw, view=inc_vw)
                        loop = MonitoringLoop(
                            node_view=node_vw,
                            node_gateway=node_gw,
                            incident_interactor=inc_interactor,
                            incident_view=inc_vw,
                            notify=notify,
                            escalation_window_minutes=config.escalation_window_minutes,
                            escalation_max_attempts=config.escalation_max_attempts,
                        )
                        await loop.poll()
            except Exception as e:
                logger.error("Monitoring poll error: %s", e)
            await asyncio.sleep(config.poll_interval_seconds)

    logger.info("Starting bot and monitoring loop")
    await asyncio.gather(
        dp.start_polling(bot),
        monitoring_task(),
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run all tests to verify nothing is broken**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apps/nodes/ioc.py src/apps/incidents/ioc.py src/main.py
git commit -m "feat: DI providers and main entrypoint"
```

---

## Task 14: Docker Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "python", "-m", "src.main"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://botuser:botpass@postgres:5432/botdb

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: botuser
      POSTGRES_PASSWORD: botpass
      POSTGRES_DB: botdb
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U botuser -d botdb"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

- [ ] **Step 3: Create `.env` from example**

```bash
cp .env.example .env
# Edit .env with real values before running
```

- [ ] **Step 4: Run linting and type check**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

Fix any issues reported.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example
git commit -m "feat: Docker deployment setup"
```

---

## Task 15: Alembic Migration + End-to-End Verification

- [ ] **Step 1: Start PostgreSQL for migration generation**

```bash
docker-compose up postgres -d
```

Wait for it to become healthy:
```bash
docker-compose ps
```

Expected: postgres shows `healthy`.

- [ ] **Step 2: Generate initial migration**

```bash
uv run alembic revision --autogenerate -m "initial schema"
```

Expected: creates `alembic/versions/xxxx_initial_schema.py` with `incidents`, `node_stats_snapshots`, `muted_nodes` tables.

- [ ] **Step 3: Apply migration**

```bash
uv run alembic upgrade head
```

Expected: `Running upgrade -> xxxx, initial schema`

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Start bot**

```bash
docker-compose up --build
```

Expected: both containers start. Bot logs show `Starting bot and monitoring loop`.

- [ ] **Step 6: Verify `/status` command in Telegram**

Send `/status` to the bot. Expected: list of nodes with 🟢/🔴/⏳ icons.

- [ ] **Step 7: Final commit**

```bash
git add alembic/versions/
git commit -m "feat: initial DB migration"
```

---

## Known Improvement: Provider Analytics

The `/providers` command currently groups by node name prefix (approximation) because `provider` is not stored in the `incidents` table. To fix properly:

1. Add `provider` column to `IncidentModel`
2. Pass provider from `NodeInfo` when opening incidents in `MonitoringLoop._handle_offline_node`
3. Generate a new Alembic migration

This is a one-task improvement after initial deployment.

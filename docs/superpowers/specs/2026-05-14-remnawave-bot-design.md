# Remnawave Admin Bot — Design Spec

**Date:** 2026-05-14
**Status:** Approved

---

## Context

Remnawave VPN nodes can go offline without the admin knowing. The goal is a Telegram bot that monitors all nodes in real time, automatically restarts them when they fall, escalates when restarts fail, and provides analytics on incidents, uptime, and traffic patterns. Two admins need equal access.

---

## Architecture

**Approach:** Single async Python process — one aiogram 3.x bot (long polling) + one APScheduler polling loop running as concurrent asyncio tasks. Two Docker containers: the bot app and PostgreSQL.

**Pattern:** Clean Architecture with Dishka DI. Two domains: `nodes` and `incidents`.

```
controllers/ → interactors/ → domain/
                           ↑
                       adapters/  ←  remnawave Python SDK
```

---

## Project Structure

```
bot_admin_samovar/
├── src/
│   ├── apps/
│   │   ├── nodes/
│   │   │   ├── domain/               # models.py, commands.py, events.py, exceptions.py
│   │   │   ├── application/
│   │   │   │   ├── interactor.py
│   │   │   │   └── interfaces/
│   │   │   │       ├── gateway.py    # Protocol (write)
│   │   │   │       └── view.py       # Protocol (read)
│   │   │   ├── adapters/             # RemnaWave SDK wrapper (gateway + view impl)
│   │   │   ├── controllers/
│   │   │   │   ├── telegram/         # /status, /node, /restart, /mute handlers
│   │   │   │   └── scheduler/        # APScheduler polling loop
│   │   │   └── ioc.py
│   │   └── incidents/
│   │       ├── domain/               # models.py, commands.py, events.py
│   │       ├── application/
│   │       │   ├── interactor.py
│   │       │   └── interfaces/
│   │       │       ├── gateway.py
│   │       │       └── view.py
│   │       ├── adapters/             # PostgreSQL implementations
│   │       ├── controllers/
│   │       │   └── telegram/         # /incidents, /stats, /worst, /providers
│   │       └── ioc.py
│   ├── infrastructure/
│   │   ├── db/                       # SQLAlchemy engine, session factory, Base
│   │   ├── remnawave/                # RemnawaveSDK initialization
│   │   └── telegram/                 # aiogram Bot, Dispatcher, admin middleware
│   ├── config.py                     # Pydantic BaseSettings
│   └── main.py                       # asyncio entrypoint
├── alembic/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env
```

---

## Tech Stack

| Tool | Role |
|---|---|
| `aiogram 3.x` | Telegram bot (long polling) |
| `remnawave` (SDK v2.7.1) | Remnawave API client |
| `APScheduler` (asyncio) | Polling scheduler |
| `SQLAlchemy 2.x async` + `asyncpg` | ORM |
| `Alembic` | DB migrations |
| `PostgreSQL 16` | Storage |
| `Dishka` | Dependency injection |
| `Pydantic BaseSettings` | Config from `.env` |
| `ruff` + `mypy strict` | Lint/types |
| `uv` | Package manager |

---

## Database Schema

### `incidents`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `node_uuid` | str | Remnawave node UUID |
| `node_name` | str | Snapshot of name at incident time |
| `started_at` | timestamp | When offline detected |
| `resolved_at` | timestamp\|null | null = active incident |
| `last_status_message` | str | Reason from API |
| `restart_attempts` | int | Auto-restart count |
| `escalated` | bool | True if 3 falls in 1 hour |
| `downtime_seconds` | int\|null | Filled on resolution |

### `node_stats_snapshots`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `node_uuid` | str | |
| `captured_at` | timestamp | |
| `users_online` | int | |
| `traffic_used_bytes` | bigint | |
| `xray_uptime` | int | Seconds |
| `is_connected` | bool | |

### `muted_nodes`
| Column | Type | Notes |
|---|---|---|
| `node_uuid` | str | PK |
| `muted_until` | timestamp | |
| `muted_by_telegram_id` | bigint | |

---

## Domain Events

| Event | Trigger | Effect |
|---|---|---|
| `NodeWentOffline` | is_connected=False, no open incident | Open incident, notify admins, attempt restart |
| `NodeRestartAttempted` | restart_node() called | Increment restart_attempts |
| `NodeEscalated` | 3 falls in last 60 min | Stop auto-restart, notify admins with 🚨 |
| `NodeCameOnline` | is_connected=True, open incident exists | Close incident, notify admins with ✅ |

---

## Monitoring Logic (Polling Loop)

Runs every **2 minutes** via APScheduler:

```
get_all_nodes() → List[NodeResponseDto]

For each node:
  1. Write snapshot to node_stats_snapshots
  2. If is_connected=False AND node not muted:
       Count incidents in last 60 min for this node
       If count < 3:
         → restart_node(uuid)
         → open/update incident
         → notify: "🔴 [NAME] упала. Причина: {msg}. Перезапуск (попытка N/3)"
       If count >= 3:
         → mark incident escalated=True
         → notify: "🚨 [NAME] не поднимается после 3 попыток. Нужен ручной разбор"
  3. If is_connected=True AND open incident exists:
       → close incident (resolved_at, downtime_seconds)
       → notify: "✅ [NAME] восстановлена. Даунтайм: N мин"
```

---

## Bot Commands

| Command | Description |
|---|---|
| `/status` | All nodes: 🟢/🔴/⏳ with country, provider, users_online |
| `/node <name>` | Detailed: uptime, traffic, xray_uptime, last incident |
| `/incidents` | Last 10 incidents with duration and cause |
| `/stats day\|week\|month` | Summary: total downtime, incident count, avg uptime% |
| `/worst` | Top-5 most problematic nodes over last month |
| `/providers` | Incident stats grouped by provider |
| `/restart <name>` | Manual restart of specific node |
| `/restart_all` | Restart all nodes (requires inline button confirmation) |
| `/mute <name> <30m\|1h\|24h>` | Suppress alerts for node for given duration |
| `/unmute <name>` | Remove mute early |

**Authorization:** Two admin Telegram IDs in `.env` (`ADMIN_IDS`). Middleware rejects all other users silently.

**UX:**
- `/restart_all` shows inline button "Да, перезапустить все" before executing
- `/status` shows compact list; inline "подробнее" button per node
- All incident notifications sent to **both** admins simultaneously

---

## Configuration (`.env`)

```env
TELEGRAM_BOT_TOKEN=...
ADMIN_IDS=123456789,987654321
REMNAWAVE_BASE_URL=https://your-panel.com
REMNAWAVE_TOKEN=...
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/botdb
POLL_INTERVAL_SECONDS=120
ESCALATION_WINDOW_MINUTES=60
ESCALATION_MAX_ATTEMPTS=3
```

---

## Deployment

```yaml
# docker-compose.yml (sketch)
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on: [postgres]
  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

---

## Verification

1. `docker-compose up` — оба контейнера стартуют без ошибок
2. Бот отвечает на `/status` в Telegram — отображает список нод
3. Симуляция: вручную отключить ноду в панели → через ≤2 мин приходит уведомление + нода перезапускается
4. После 3 падений за час — приходит уведомление 🚨 об эскалации
5. `/incidents` показывает записи из БД
6. `/mute <name> 30m` — уведомления по ноде не приходят в течение 30 минут
7. `/restart_all` — кнопка подтверждения появляется, после нажатия все ноды рестартуют

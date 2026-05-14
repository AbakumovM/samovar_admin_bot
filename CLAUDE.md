# CLAUDE.md — Remnawave Admin Bot

## Что это

Telegram-бот для мониторинга VPN-нод в Remnawave-панели.
Два администратора (Telegram ID в `ADMIN_IDS`), права одинаковые.

## Стек

- Python 3.12, uv, ruff, mypy strict
- aiogram 3.x — Telegram, long polling
- dishka 1.x — DI (`@inject` обязателен на каждом хендлере с `FromDishka[T]`)
- remnawave SDK 2.7.1 — API-клиент нод
- SQLAlchemy 2.x async + asyncpg + Alembic — БД
- PostgreSQL 16
- Docker + docker-compose

## Архитектура

Clean Architecture, два домена:

```
src/apps/nodes/       — мониторинг, рестарты, мут
src/apps/incidents/   — история инцидентов, аналитика, отчёты
src/infrastructure/   — db, remnawave client, telegram setup
src/config.py         — pydantic BaseSettings
src/main.py           — точка входа, сборка контейнера
```

### Ключевые файлы

| Файл | Назначение |
|---|---|
| `src/apps/nodes/controllers/scheduler/loop.py` | Логика мониторинга (`poll`, `poll_offline`) |
| `src/apps/nodes/controllers/scheduler/tasks.py` | Asyncio-таски мониторинга |
| `src/apps/incidents/controllers/scheduler/tasks.py` | Таск ежедневного отчёта + форматирование |
| `src/apps/nodes/controllers/telegram/handlers.py` | Команды /status /node /restart /mute |
| `src/apps/incidents/controllers/telegram/handlers.py` | Команды /incidents /stats /worst /providers /report |
| `src/infrastructure/telegram/middleware.py` | AdminAuthMiddleware — фильтр по ADMIN_IDS |

## Логика мониторинга

Два цикла в `asyncio.gather`:

- **Основной** (`poll_interval_seconds=120`) — все ноды, записывает снапшоты
- **Быстрый** (`fast_poll_interval_seconds=30`) — только ноды с открытым инцидентом, без снапшотов

```
Каждый тик:
  is_disabled → пропустить
  is_connected=False → _handle_offline_node
  is_connected=True + открытый инцидент → _handle_online_node (закрыть)
```

### Эскалационная логика (`_handle_offline_node`)

Счётчик берётся из `open_incident.restart_attempts` (не из количества инцидентов в окне):

```
restart_attempts < max_attempts → restart + уведомление "попытка N/M"
restart_attempts >= max_attempts → эскалация 🚨 + стоп (больше не рестартует)
```

`escalation_max_attempts=3` по умолчанию.

## Команды бота

| Команда | Описание |
|---|---|
| `/status` | Все ноды с иконками статуса |
| `/node <имя>` | Детали по ноде |
| `/incidents` | Последние 10 инцидентов |
| `/stats day\|week\|month` | Статистика за период |
| `/worst` | Топ-5 проблемных нод за 30 дней |
| `/providers` | Инциденты по префиксам имён нод |
| `/report` | Ежедневный отчёт по запросу (последние 24ч) |
| `/restart <имя>` | Рестарт ноды |
| `/restart_all` | Рестарт всех нод (с подтверждением) |
| `/mute <имя> 30m\|1h\|24h` | Заглушить алерты |
| `/unmute <имя>` | Снять мут |

## Ежедневный отчёт

Приходит автоматически каждый день в **20:00 МСК** (17:00 UTC).
Настраивается через `DAILY_REPORT_HOUR_UTC=17` в `.env`.
По запросу — `/report`.

## БД (таблицы)

- `incidents` — инциденты (node_uuid, started_at, resolved_at, restart_attempts, escalated, downtime_seconds)
- `node_stats_snapshots` — снапшоты каждые 2 мин
- `muted_nodes` — замьюченные ноды (node_uuid, muted_until)

## Конфиг (.env)

```
TELEGRAM_BOT_TOKEN=
ADMIN_IDS=[111111111,222222222]   # JSON-формат обязателен
REMNAWAVE_BASE_URL=
REMNAWAVE_TOKEN=
DATABASE_URL=                     # переопределяется docker-compose, можно не ставить
POLL_INTERVAL_SECONDS=120
FAST_POLL_INTERVAL_SECONDS=30
ESCALATION_WINDOW_MINUTES=60
ESCALATION_MAX_ATTEMPTS=3
DAILY_REPORT_HOUR_UTC=17
```

**Важно**: `ADMIN_IDS` должен быть в JSON-формате `[id1,id2]`.

## Деплой

```bash
# Локально
docker-compose up -d

# Прод (без проброса порта postgres)
docker compose -f docker-compose.prod.yml up -d

# Миграции
docker compose -f docker-compose.prod.yml run --rm bot uv run alembic upgrade head

# Логи
docker compose -f docker-compose.prod.yml logs -f bot
```

## Известные особенности

- `@inject` обязателен на каждом aiogram-хендлере с `FromDishka[T]` (dishka 1.x)
- `setup_dishka` должен вызываться ДО `dp.include_router()`
- Disabled-ноды пропускаются полностью (API возвращает 400 при рестарте)
- `.dockerignore` исключает `.env` из образа — переменные передаются через docker-compose `env_file`

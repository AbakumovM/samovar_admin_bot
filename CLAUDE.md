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
- maxminddb — чтение GeoLite2-ASN (опционально, для антифрод ASN-группировки)
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
| `/top_traffic [day\|week\|month]` | Топ-10 потребителей трафика за период |
| `/anomalies` | Пользователи с аномальным трафиком сегодня |
| `/user_traffic <имя>` | Трафик пользователя за 7 дней |
| `/billing` | Предстоящие платежи нод, статистика, кнопки оплаты |
| `/billing_history` | Последние 10 записей платежей |
| `/antifraud_check` | Разовая проверка на шеринг подписки (не дожидаясь расписания) |
| `/restart <имя>` | Рестарт ноды |
| `/restart_all` | Рестарт всех нод (с подтверждением) |
| `/mute <имя> 30m\|1h\|24h` | Заглушить алерты |
| `/unmute <имя>` | Снять мут |

## Ежедневный отчёт

Приходит автоматически каждый день в **20:00 МСК** (17:00 UTC).
Настраивается через `DAILY_REPORT_HOUR_UTC=17` в `.env`.
По запросу — `/report`.

## Антифрод (шеринг подписки по конкурентным IP)

`src/apps/antifraud/`. Раз в `ANTIFRAUD_SCAN_INTERVAL_SECONDS` (по умолчанию
30 мин) последовательно опрашивает все ноды через `/api/connections/by-node/*`
(нативный модуль панели 3.2.3, поверх Xray-core online-IP трекера, минус
`ANTIFRAUD_IGNORED_NODE_UUIDS`), агрегирует IP по пользователям, отбрасывает
IP из `ANTIFRAUD_IP_WHITELIST` и записи старше `ANTIFRAUD_IP_RECENCY_SECONDS`
(по умолчанию 60 сек — Xray-core на практике копит записи дольше, чем
«прямо сейчас»). Резолвинг лимита — точечный `GET /api/users/{id}` только
для реально подключённых кандидатов (не полный проход по всем
пользователям), с in-process кэшем на `ANTIFRAUD_USER_CACHE_TTL_SECONDS`.
На панели с тысячами одновременных подключений последовательный резолвинг
не укладывается в интервал скана — запросы идут с ограниченным
параллелизмом (`ANTIFRAUD_USER_RESOLVE_CONCURRENCY`, по умолчанию 8, как у
remnawave-limiter для той же задачи).

`hwidDeviceLimit = null` или `= 0` — пользователь не проверяется (0
намеренно трактуется как «без ограничений», не как «ноль устройств» —
отличается от семантики нативной HWID-фичи панели, осознанное решение).
Пользователи из `ANTIFRAUD_WHITELIST_USER_IDS` тоже пропускаются.

Порог: `hwidDeviceLimit + ANTIFRAUD_IP_SLACK + floor(hwidDeviceLimit ×
ANTIFRAUD_IP_SLACK_MULTIPLIER)` — «жёсткий» (действие), выше него — алерт с
кнопкой отключения. Опционально, между голым лимитом и жёстким порогом —
«мягкий» уровень (`ANTIFRAUD_SOFT_ALERTS_ENABLED`, по умолчанию выкл):
только информационный алерт, без действия, свой отдельный cooldown.

Группировка вместо сырых IP (снижает ложные срабатывания от роуминга
одного устройства): `ANTIFRAUD_SUBNET_GROUPING` (по `/24`) или
`ANTIFRAUD_ASN_GROUPING` (по провайдеру, через MaxMind GeoLite2-ASN —
требует `ANTIFRAUD_MAXMIND_ACCOUNT_ID`/`ANTIFRAUD_MAXMIND_LICENSE_KEY`,
бесплатный аккаунт на maxmind.com; база скачивается и обновляется
автоматически раз в `ANTIFRAUD_MAXMIND_UPDATE_INTERVAL_HOURS`).

Перед алертом — накопление нарушений: срабатывание не с первого раза, а
после `ANTIFRAUD_VIOLATION_THRESHOLD` превышений подряд в окне
`ANTIFRAUD_VIOLATION_WINDOW_SECONDS` (по умолчанию threshold=1 — как
раньше, алерт сразу).

Только уведомление админам батч-дайджестом с cooldown
(`ANTIFRAUD_COOLDOWN_HOURS`, по умолчанию 24ч) — без авто-кика. В дайджесте
каждый IP — кликабельная ссылка на ipinfo.io, кнопка ручного отключения
(`POST /connections/drop`, требует отдельный write-скоуп токена). По
умолчанию выключено (`ANTIFRAUD_ENABLED=false`). По запросу —
`/antifraud_check`.

**Авто-блок по 3 критериям** — система многоуровневой проверки перед блокировкой подписки:
пользователь помечается как подозрительный, если выполняются хотя бы 2 из 3 условий:
(1) превышен общий порог конкурентных IP (`hwidDeviceLimit` + `ANTIFRAUD_IP_SLACK`);
(2) обнаружена концентрация подключений на RU-нодах выше `ANTIFRAUD_RU_NODE_IP_THRESHOLD`;
(3) отсутствует активная платёж в системе samovarbot (проверяется через `GET /internal/users/{id}/subscription`).
При `criteria_matched >= 2` в дайджесте антифрода появляется кнопка «Заблокировать» (требует
известного `telegram_id` пользователя), позволяющая администратору ручных блокировать подписку —
вызывает `POST /internal/users/{id}/block` на samovarbot и переводит подписку в `DISABLED` в панели.
При `criteria_matched == 3` и включённом `ANTIFRAUD_AUTO_BLOCK_ENABLED=true` блокировка
выполняется автоматически без кнопки, уведомление приходит как батч-дайджест авто-блоков.
По умолчанию авто-блок выключен (`ANTIFRAUD_AUTO_BLOCK_ENABLED=false`), кнопка и
дайджесты работают независимо.

## БД (таблицы)

- `incidents` — инциденты (node_uuid, started_at, resolved_at, restart_attempts, escalated, downtime_seconds)
- `node_stats_snapshots` — снапшоты каждые 2 мин
- `muted_nodes` — замьюченные ноды (node_uuid, muted_until)
- `user_traffic_last_snapshot` — последний снапшот трафика каждого пользователя (для вычисления дельты)
- `user_traffic_daily` — дневные агрегаты потребления по пользователям (user_uuid, date, bytes_consumed, anomaly_alerted)
- `antifraud_notified_users` — cooldown уведомлений антифрода (remnawave_id, notified_at, soft_notified_at)
- `antifraud_violation_counts` — накопление нарушений антифрода перед алертом (remnawave_id, count, window_expires_at)

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
TRAFFIC_CHECK_INTERVAL_SECONDS=3600
TRAFFIC_ANOMALY_THRESHOLD_GB=30.0
TRAFFIC_ANOMALY_MULTIPLIER=2.0
BILLING_CURRENCY=$               # Символ валюты, по умолчанию: $
BILLING_ALERT_DAYS_BEFORE=3      # За сколько дней алертить, по умолчанию: 3
BILLING_CHECK_HOUR_UTC=17        # Час UTC ежедневной проверки, по умолчанию: 17
ANTIFRAUD_ENABLED=false                    # Включить антифрод-скан, по умолчанию: false
ANTIFRAUD_SCAN_INTERVAL_SECONDS=1800       # Интервал полного прохода по нодам, по умолчанию: 1800 (30 мин)
ANTIFRAUD_IP_SLACK=2                       # Запас сверх hwidDeviceLimit пользователя при расчёте порога
ANTIFRAUD_IP_SLACK_MULTIPLIER=0.0          # Доп. пропорциональный запас: + floor(лимит × множитель)
ANTIFRAUD_IP_RECENCY_SECONDS=60            # Учитывать только IP с lastSeen не старше N сек (реальная одновременность)
ANTIFRAUD_COOLDOWN_HOURS=24                # Не уведомлять повторно про одного юзера чаще, по умолчанию: 24
ANTIFRAUD_JOB_POLL_INTERVAL_SECONDS=1.0    # Интервал поллинга job на ноде
ANTIFRAUD_JOB_POLL_TIMEOUT_SECONDS=15.0    # Таймаут поллинга job на одной ноде
ANTIFRAUD_USER_CACHE_TTL_SECONDS=300.0     # TTL кэша GET /users/{id} на время процесса
ANTIFRAUD_USER_RESOLVE_CONCURRENCY=8       # Параллелизм точечных GET /users/{id} на скан
ANTIFRAUD_IGNORED_NODE_UUIDS=[]            # JSON-массив UUID нод, пропускаемых при сборе
ANTIFRAUD_IP_WHITELIST=[]                  # JSON-массив IP/CIDR, исключаемых из подсчёта
ANTIFRAUD_WHITELIST_USER_IDS=[]            # JSON-массив numeric id пользователей, пропускаемых целиком
ANTIFRAUD_SOFT_ALERTS_ENABLED=false        # Информационный алерт при превышении голого лимита (без действия)
ANTIFRAUD_VIOLATION_THRESHOLD=1            # Срабатываний подряд нужно для алерта, 1 = сразу
ANTIFRAUD_VIOLATION_WINDOW_SECONDS=3600    # Окно накопления нарушений
ANTIFRAUD_SUBNET_GROUPING=false            # Считать уникальные /24-подсети вместо сырых IP
ANTIFRAUD_SUBNET_PREFIX_V4=24              # Длина IPv4-префикса для группировки
ANTIFRAUD_ASN_GROUPING=false               # Считать уникальные ASN-провайдеры (приоритетнее subnet)
ANTIFRAUD_MAXMIND_ACCOUNT_ID=              # Аккаунт MaxMind, нужен для ASN-группировки
ANTIFRAUD_MAXMIND_LICENSE_KEY=             # Лицензионный ключ MaxMind (бесплатный)
ANTIFRAUD_ASN_DATABASE_PATH=./geoip/GeoLite2-ASN.mmdb  # Путь к базе GeoLite2-ASN
ANTIFRAUD_MAXMIND_UPDATE_INTERVAL_HOURS=168  # Интервал автообновления базы (недельный по умолчанию)
ANTIFRAUD_AUTO_BLOCK_ENABLED=false         # Авто-блок при 3/3 критериях, по умолчанию: false
ANTIFRAUD_RU_NODE_PREFIXES=["RU"]          # Префиксы имён нод, считающихся RU для критерия концентрации
ANTIFRAUD_RU_NODE_IP_THRESHOLD=2           # Порог IP именно на RU-нодах (не зависит от hwidDeviceLimit)
SAMOVARBOT_BASE_URL=                        # Базовый URL сервиса подписок (samovarbot)
SAMOVARBOT_INTERNAL_API_KEY=                # Ключ для internal API samovarbot (X-Internal-Api-Key)
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

## Правила работы с проектом

- Папка `docs/` не коммитится в git — это локальные заметки и планы.

## Известные особенности

- `@inject` обязателен на каждом aiogram-хендлере с `FromDishka[T]` (dishka 1.x)
- `setup_dishka` должен вызываться ДО `dp.include_router()`
- Disabled-ноды пропускаются полностью (API возвращает 400 при рестарте)
- `.dockerignore` исключает `.env` из образа — переменные передаются через docker-compose `env_file`

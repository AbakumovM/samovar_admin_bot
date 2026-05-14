# Remnawave Admin Bot

Telegram-бот для мониторинга VPN-нод в Remnawave. Автоматически рестартует упавшие ноды, эскалирует если 3 падения за час, ведёт историю инцидентов.

---

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose
- Telegram-бот (создать через [@BotFather](https://t.me/BotFather))
- API-токен Remnawave

---

## Локальный запуск

### 1. Настроить окружение

```bash
cp .env.example .env
```

Заполнить `.env`:

```env
TELEGRAM_BOT_TOKEN=токен_от_BotFather
ADMIN_IDS=твой_telegram_id,второй_admin_id      # через запятую, без пробелов
REMNAWAVE_BASE_URL=https://твоя-панель.com
REMNAWAVE_TOKEN=токен_из_раздела_API_Tokens
DATABASE_URL=postgresql+asyncpg://botuser:botpass@localhost:5432/botdb
```

> Свой Telegram ID можно узнать у [@userinfobot](https://t.me/userinfobot).

### 2. Установить зависимости

```bash
uv sync
```

### 3. Поднять PostgreSQL

```bash
docker-compose up postgres -d
```

Подождать ~5 секунд пока postgres будет готов:

```bash
docker-compose ps   # postgres должен быть healthy
```

### 4. Применить миграцию

```bash
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
```

### 5. Запустить бота

```bash
uv run python -m src.main
```

Бот запустится и начнёт опрашивать ноды каждые 2 минуты. В терминале будут видны логи.

---

## Деплой на сервере

```bash
# Заполнить .env (DATABASE_URL уже прописан в docker-compose.yml для контейнера)
cp .env.example .env
nano .env

# Поднять postgres, сгенерировать миграцию
docker-compose up postgres -d
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head

# Запустить всё
docker-compose up --build -d

# Логи
docker-compose logs -f bot
```

> При деплое `DATABASE_URL` в `.env` для контейнера переопределяется через `environment` в `docker-compose.yml` — менять не нужно.

---

## Команды бота

| Команда | Описание |
|---|---|
| `/status` | Состояние всех нод (🟢/🔴/⏳) |
| `/node <имя>` | Детали по конкретной ноде |
| `/incidents` | Последние 10 инцидентов |
| `/stats day\|week\|month` | Статистика за период |
| `/worst` | Топ-5 проблемных нод за месяц |
| `/providers` | Инциденты по регионам |
| `/restart <имя>` | Ручной рестарт ноды |
| `/restart_all` | Рестарт всех нод (с подтверждением) |
| `/mute <имя> 30m\|1h\|24h` | Заглушить алерты по ноде |
| `/unmute <имя>` | Снять мут |

---

## Алерты

Бот отправляет уведомления **обоим** администраторам:

- 🔴 Нода упала → автоматический рестарт (попытка N/3)
- 🚨 3 падения за час → эскалация, рестарты остановлены
- ✅ Нода восстановлена → инцидент закрыт, указан даунтайм

---

## Параметры (`.env`)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POLL_INTERVAL_SECONDS` | `120` | Интервал опроса нод |
| `ESCALATION_WINDOW_MINUTES` | `60` | Окно для подсчёта падений |
| `ESCALATION_MAX_ATTEMPTS` | `3` | Попыток до эскалации |

---

## Разработка

```bash
uv run pytest                          # тесты
uv run ruff check src/ tests/          # линтинг
uv run ruff format src/ tests/         # форматирование
uv run mypy src/                       # проверка типов
```

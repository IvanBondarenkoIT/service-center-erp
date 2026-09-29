# Service Center ERP

Лёгкий сервисный учёт ремонтов кофеварок: Postgres + FastAPI + Jinja/HTMX.

**Главный ключ истории аппарата — серийный номер.** Телефон клиента — вторичный (привезти может другой человек).

## Быстрый старт (local)

### Вариант A — Docker Compose (Postgres + app)

```powershell
copy .env.example .env
docker compose up --build
```

Открыть: http://localhost:8080

### Вариант B — без Docker (SQLite)

В `.env` поставьте:

```
DATABASE_URL=sqlite:///./scerp_local.db
```

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# поправьте DATABASE_URL на sqlite как выше
uvicorn app.main:app --reload --port 8080
```

### Без Docker (приложение локально, БД Postgres в compose)

```powershell
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# DATABASE_URL уже на localhost:5433
uvicorn app.main:app --reload --port 8080
```

### Пользователи по умолчанию

| Логин | Пароль | Роль |
|-------|--------|------|
| `admin` | `admin123` | все заказы + отчёты |
| `mechanic_batumi` | `mechanic123` | только свои заказы, СЦ Батуми |
| `mechanic_tbilisi1` | `mechanic123` | только свои, Тбилиси 1 |
| `mechanic_tbilisi2` | `mechanic123` | только свои, Тбилиси 2 |
| `accountant` | `accountant123` | касса: просмотр и печать, без заказов |

Пароли: `SEED_ADMIN_PASSWORD` / `SEED_MECHANIC_PASSWORD` / `SEED_ACCOUNTANT_PASSWORD`, либо свой на логин `SEED_PASSWORD_MECHANIC_BATUMI`. Состав пользователей — `SEED_USERS` (без правки кода). В проде не оставлять значения из `.env.example`.

## Возможности

- Заказ = шапка (дата, механик, СЦ, кофеварка, клиент, причина, комментарий) + строки (работа/запчасть/расход/гарантия/диагностика)
- Словари клиент (телефон→имя) и кофеварка (серийник→модель) с созданием с формы
- Мягкая связь клиент↔кофеварка (автоподстановка, не жёсткая)
- История обращений по серийнику
- Админ-отчёты: суммы по центру/оплате, топ причин, повторные SN
- Импорт Excel текущей таблицы сервиса
- Кеш каталога моделей/запчастей из Firebird через HTTP-proxy (как в granit-daily-sales-bot)

## Импорт Excel

```powershell
python scripts/import_excel.py
# или
python scripts/import_excel.py "D:\path\Coffee Machines Table 2025.xlsx" --center tbilisi
```

Строки без серийника аппарата получают placeholder `NEED-SERIAL-…` и флаг «нужен SN».

Кассовая книга (расход / инкасация / opening, не приход B/D):

```powershell
python scripts/import_cash_xlsx.py --center batumi --user admin
```

## Синк каталога ERP

В `.env` задать `PROXY_API_URL` и `PROXY_API_TOKEN` (скопировать из `granit-daily-sales-bot/.env`), затем:

```powershell
# Инкрементальный (по умолчанию): только новые ID + обновление устаревших
python scripts/sync_erp_catalog.py
python scripts/sync_erp_catalog.py --mode incremental

# Полный обход пакетами (редко, если нужно пересобрать кеш)
python scripts/sync_erp_catalog.py --mode full
```

или кнопки в UI (admin) → `/dict/erp-catalog`.

Параметры бережного синка в `.env`:

- `ERP_SYNC_BATCH_SIZE=150` — строк за запрос
- `ERP_SYNC_PAUSE_MS=500` — пауза между пакетами
- `ERP_SYNC_MAX_BATCHES=20` — лимит пакетов за один запуск
- `ERP_SYNC_REFRESH_BATCH=100` — сколько старых записей обновить за инкремент

Данные хранятся в локальной таблице `erp_goods_cache`; UI **не** ходит в Firebird при каждом клике.

## Продакшен

Прод: **https://service.dimkava.ge** — альт-сервер `85.114.224.45` (Debian, Docker) за Caddy.
Архитектура сервера: `D:\CursorProjects\ssh-alternative-server-connection\docs\ARCHITECTURE-ALT.md`.
Подробности: [`deploy/README.md`](deploy/README.md).

- **База:** общий Postgres `pg-core`, база `granit`, роль и схема `scerp` (`search_path = scerp, core`).
  Таблицы приложения — в `scerp`; `core` (данные Granit, ночной ETL) — только чтение; в `public` ничего не создаётся.
  Проверка на Postgres: `PG_ADMIN_URL=postgresql://postgres:<pwd>@localhost:5432/granit python scripts/check_pg_schema.py --reset`.
- **Компоуз:** [`deploy/docker-compose.prod.yml`](deploy/docker-compose.prod.yml) — только приложение, образ из GHCR,
  сети `pgnet` + `edge`, на хосте `127.0.0.1:8090` для health-проверки.
- **CI/CD:** [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml). PR и push → pytest + проверка схемы на Postgres;
  push в `main` → образ `ghcr.io/ivanbondarenkoit/service-center-erp:main` и `:sha-xxxxxxx`.
  Сервер раз в 5 минут делает `docker compose pull` и перезапускает контейнер, если образ изменился
  (с проверкой `/health` и автооткатом) — выкладка не дольше ~5 минут после push.
- **Откат вручную:** `IMAGE_TAG=sha-xxxxxxx` в `.env` на сервере.
- **Схема БД:** только обратно совместимые изменения (добавить таблицу/колонку; не переименовывать и не удалять
  в одном релизе). Миграции (`create_all` + `ensure_schema`) идут при старте контейнера.
- **Безопасность:** `APP_ENV=production` запрещает старт с дефолтным `SECRET_KEY` и дефолтными паролями seed;
  `SESSION_COOKIE_SECURE=true` за HTTPS. Uvicorn запущен с `--proxy-headers`.
- **Деплой** запускает хаб: `python scripts/deploy_app.py service-center-erp` в `ssh-alternative-server-connection`.

## Railway (только демо)

Прод — на альт-сервере (см. выше); Railway оставлен как демо-стенд.

Чеклист: [`docs/DEPLOY_RAILWAY.md`](docs/DEPLOY_RAILWAY.md). Корень деплоя — **этот** репозиторий, не `apps/service-center-erp`.

1. GitHub → Railway project, builder Dockerfile.
2. PostgreSQL plugin (`DATABASE_URL`).
3. Variables: `SECRET_KEY`, `SEED_*` включая accountant (см. [`railway.env.example`](railway.env.example)).
4. Cron Schedule **пустой**. Variables: `PORT=8080`. Uvicorn слушает `$PORT` (везде 8080).
5. Smoke: `GET /health`.

`PROXY_API_*` на демо можно не задавать.

## Структура

```
app/           # FastAPI, models, routers, services, i18n
templates/     # Jinja UI
static/        # CSS/JS
scripts/       # seed, import_excel, import_cash_xlsx, sync_erp_catalog
docs/          # DEPLOY_RAILWAY.md (демо)
deploy/        # prod compose для альт-сервера (pg-core, GHCR)
.github/       # CI/CD
alembic/       # миграции
```

## Health

`GET /health` → `{"status":"ok"}`

## Порты (локально)

| Проект | Порт |
|--------|------|
| Service Center ERP | **8080** |
| Promocode Checker | 8020 |
| Firebird proxy | 8010 |

## Troubleshooting: вижу чужой UI (Promocode Checker и т.п.)

Сервер может отвечать правильно, а браузер показывать старое PWA с **service worker**, зарегистрированным на том же origin (хост + порт).

1. Откройте ERP: http://127.0.0.1:8080/login (не 8020).
2. Если на **8020** всё ещё виден Promocode Checker — очистите старый origin:
   - F12 → **Application** → **Service Workers** → Unregister для `127.0.0.1:8020`
   - **Storage** → **Clear site data**
   - `Ctrl+Shift+R`
3. Проверка: http://127.0.0.1:8080/health должен вернуть `"app": "Service Center ERP"`.
4. InPrivate/Incognito — быстрый способ убедиться, что это кэш браузера, а не сервер.

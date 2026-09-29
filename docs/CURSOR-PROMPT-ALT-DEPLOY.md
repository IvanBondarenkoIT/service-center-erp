# Промпт для Cursor: подготовка service-center-erp к деплою на альт-сервер

Скопируй блок ниже в чат Cursor, открыв этот репозиторий.

---

Подготовь service-center-erp к продакшен-деплою на наш альт-сервер и настрой CI/CD. Сам деплой не запускай — его делает deploy hub (`D:\CursorProjects\ssh-alternative-server-connection`) командой `python scripts/deploy_app.py service-center-erp`. Архитектура целиком: `D:\CursorProjects\ssh-alternative-server-connection\docs\ARCHITECTURE-ALT.md`.

## Контекст: что уже есть на сервере

- Сервер `85.114.224.45` (Debian 13, Docker). Приложение будет жить в `~/apps/service-center-erp/`.
- **Общий Postgres `pg-core`** (Postgres 16) в Docker-сети `pgnet`. База `granit`, у приложения своя роль и схема `scerp`:
  - `search_path` роли `scerp` = `scerp, core`, так что таблицы создаются в `scerp`, а общие данные Granit (схема `core`, наполняется ночным ETL) видны на чтение;
  - в `public` создавать ничего нельзя; в `core` — только чтение;
  - строка подключения: `DATABASE_URL=postgresql://scerp:<пароль>@pg-core:5432/granit` (пароль положит хаб в `.env` на сервере).
- **Reverse proxy `edge`** (Caddy) на 80/443 в Docker-сети `edge`. Домен `https://service.dimkava.ge` уже выдаёт HTTPS (Let's Encrypt), сейчас там заглушка; хаб переключит её на `reverse_proxy service-center-erp:8080`.
- Порт 8080 на хосте занят notify-hub. Приложению на хосте нужен только `127.0.0.1:8090` для health-проверки хаба.

## Что сделать

### 1. `deploy/docker-compose.prod.yml` — без своего Postgres

```yaml
name: service-center-erp

services:
  app:
    image: ghcr.io/ivanbondarenkoit/service-center-erp:${IMAGE_TAG:-main}
    container_name: service-center-erp
    restart: unless-stopped
    env_file:
      - .env
    environment:
      PORT: "8080"
      TZ: Asia/Tbilisi
    ports:
      - "127.0.0.1:8090:8080"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks:
      - pgnet
      - edge

networks:
  pgnet:
    external: true
  edge:
    external: true
```

- Сервис `db` и volume `scerp_prod_pgdata` убрать из прод-компоуза. Локальный `docker-compose.yml` для разработки оставить как есть (со своим Postgres).
- Хаб кладёт этот файл на сервер как `~/apps/service-center-erp/docker-compose.prod.yml`, `.env` рядом.

### 2. Схема `scerp` вместо `public`

- Убедиться, что `Base.metadata.create_all` (`app/main.py`) и `ensure_schema()` (`app/services/db_migrate.py`) работают в схеме из `search_path`: не хардкодить `public`, `inspect(engine).get_table_names()` без явного `schema=` (вернёт `current_schema()` = `scerp`).
- Enum-типы (`CREATE TYPE order_status`, `ALTER TYPE user_role ADD VALUE`) должны создаваться в `scerp`. Проверить, что нет запросов к `information_schema`/`pg_type` с фильтром по `public`.
- Добавить тест или скрипт-проверку для Postgres: подключение ролью с `search_path=scerp,core`, старт приложения, все таблицы и типы в схеме `scerp`. Для локальной проверки можно поднять Postgres, создать роль и схему так же, как на сервере:
  ```sql
  CREATE ROLE scerp LOGIN PASSWORD 'scerp';
  CREATE SCHEMA scerp AUTHORIZATION scerp;
  CREATE SCHEMA core;
  GRANT USAGE ON SCHEMA core TO scerp;
  ALTER ROLE scerp SET search_path = scerp, core;
  REVOKE CREATE ON SCHEMA public FROM PUBLIC;
  ```

### 3. Работа за HTTPS-прокси

- `Dockerfile`: запуск uvicorn с `--proxy-headers --forwarded-allow-ips='*'`, чтобы редиректы и URL строились с `https://` (Caddy передаёт `X-Forwarded-Proto`).
- Cookie: добавить настройку `session_cookie_secure: bool = False` в `Settings` (`app/config.py`, env `SESSION_COOKIE_SECURE`) и передавать `secure=settings.session_cookie_secure` во все `set_cookie` и `delete_cookie` в `app/routers/auth.py` (сессия и локаль). На сервере будет `SESSION_COOKIE_SECURE=true`, локально — `false`.
- `/health` не требует авторизации и не ходит в внешние сервисы (уже так — оставить).

### 4. Безопасный первый старт

- Если `SECRET_KEY` равен дефолтному `change-me-in-production` и приложение не в режиме разработки — не стартовать (понятная ошибка в лог). Аналогично для дефолтных `SEED_*` паролей в проде.
- В `.env.example` добавить блок «Альт-сервер»: `DATABASE_URL` (pg-core), `SECRET_KEY`, `SEED_*`, `SESSION_COOKIE_SECURE=true`, `PROXY_API_*`. Реальные значения не коммитить.

### 5. CI/CD: push в `main` = автовыкладка

Создать `.github/workflows/ci-cd.yml`:

```yaml
name: ci-cd

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pytest -q

  image:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/ivanbondarenkoit/service-center-erp
          tags: |
            type=raw,value=main
            type=sha,prefix=sha-
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- Тесты должны проходить в CI без Postgres (SQLite) и без `.env`.
- После первого успешного push: в GitHub → Packages → `service-center-erp` → Package settings → **Change visibility → Public** (серверу не нужен логин в GHCR).
- Как работает выкладка: сервер каждые 5 минут делает `docker compose pull`; если образ `:main` изменился — перезапускает контейнер, ждёт `/health`, при провале откатывает на прошлый образ. Ручной откат: `IMAGE_TAG=sha-xxxxxxx` в `.env` на сервере.
- Изменения схемы БД — только обратно совместимые (добавить колонку/таблицу, не переименовывать и не удалять в одном релизе): миграции идут при старте контейнера.

### 6. Документация

- `README.md`: раздел «Продакшен» — `https://service.dimkava.ge`, альт-сервер, pg-core/схема `scerp`, CI/CD (push в `main` → выкладка ≤5 минут), откат через `IMAGE_TAG`. Ссылка на `docs/ARCHITECTURE-ALT.md` хаба.
- `docs/DEPLOY_RAILWAY.md`: пометить, что Railway — только демо; прод на альт-сервере.
- `tests/test_stage7_deploy.py`: обновить под новый прод-компоуз (нет сервиса `db`, есть сети `pgnet`/`edge`, `image` из GHCR, порт `127.0.0.1:8090`).

## Ограничения

- Не деплоить и не трогать сервер; не менять Railway-демо.
- Не коммитить секреты (`.env`, пароли, токены прокси).
- `pytest -q` зелёный перед коммитом.
- Когда закончишь — кратко перечисли изменения и что нужно от хаба (переменные `.env`, пароль роли `scerp`), чтобы я запустил деплой.

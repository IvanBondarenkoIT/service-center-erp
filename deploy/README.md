# Продакшен — Service Center ERP

Прод живёт на альт-сервере `85.114.224.45` за Caddy (`https://service.dimkava.ge`).
Архитектура: `D:\CursorProjects\ssh-alternative-server-connection\docs\ARCHITECTURE-ALT.md`.

## Деплой

Деплоит deploy hub, не этот репозиторий:

```powershell
cd D:\CursorProjects\ssh-alternative-server-connection
python scripts/deploy_app.py service-center-erp
```

Хаб кладёт `docker-compose.prod.yml` и `.env` в `~/apps/service-center-erp/` на сервере.

- Образ: `ghcr.io/ivanbondarenkoit/service-center-erp:${IMAGE_TAG:-main}` (собирает GitHub Actions при push в `main`).
- Сети: `pgnet` (общий Postgres `pg-core`) и `edge` (Caddy). Обе внешние, их создаёт хаб.
- На хосте открыт только `127.0.0.1:8090` для health-проверки хаба; снаружи трафик идёт через Caddy.
- Сервер раз в 5 минут делает `docker compose pull`; если `:main` изменился — перезапуск, ожидание `/health`, при провале откат.
- Ручной откат: `IMAGE_TAG=sha-xxxxxxx` в `.env` на сервере.

## База данных

- Своего Postgres в прод-компоузе нет. База `granit` в `pg-core`, роль и схема `scerp`
  (`search_path = scerp, core`): таблицы приложения в `scerp`, `core` (данные Granit из ночного ETL) — только чтение.
- Бэкапы делает хаб на уровне `pg-core`.
- Изменения схемы — только обратно совместимые (добавить таблицу/колонку). Миграции идут при старте контейнера.

## `.env` на сервере

См. блок «Альт-сервер» в `.env.example`: `APP_ENV=production`, `DATABASE_URL`, `SECRET_KEY`,
`SEED_*`, `SESSION_COOKIE_SECURE=true`, `PROXY_API_*`. С дефолтными `SECRET_KEY` или паролями seed
приложение в продакшене не стартует.

## После первого старта

1. Войти как `admin`, проверить пароли пользователей (seed создаёт только отсутствующих).
2. `/dict/erp-catalog` → синк: модели кофеварок и клиенты из Гранита.
3. При необходимости — импорт Excel с машины, где лежит xlsx.

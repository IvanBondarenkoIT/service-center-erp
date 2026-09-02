# Деплой на Railway

Образец: [stock-safety-monitor](https://github.com/IvanBondarenkoIT/stock-safety-monitor) → Railway.  
Отличия: это **web** (uvicorn), не cron; нужен **PostgreSQL**.

Публичный репозиторий: [IvanBondarenkoIT/service-center-erp](https://github.com/IvanBondarenkoIT/service-center-erp).

## Чеклист

- [ ] Код в GitHub, Railway: New Project → этот репозиторий → Dockerfile
- [ ] **Root Directory** пустой (корень репо, не `apps/service-center-erp`)
- [ ] В Settings сервиса **Cron Schedule пустой** (long-running web, не job)
- [ ] Plugin **PostgreSQL** → Railway сам даст `DATABASE_URL` (`postgres://…` нормализуется в приложении)
- [ ] Variables из [`railway.env.example`](../railway.env.example): `SECRET_KEY`, `SEED_*` (не `admin123` в проде)
- [ ] `PROXY_API_*` опционально: без них каталог ERP пустой, заказы работают
- [ ] `healthcheckPath` = `/health` (уже в `railway.toml`)
- [ ] Smoke: `GET https://<host>/health` → `{"status":"ok"}`; логин admin / mechanic / accountant
- [ ] Рестарт сервиса — заказы остаются в Postgres

Не коммитить: `.env`, `.venv`, `*.db`, живые `data/input/*.xlsx`.

## Переменные (обязательные)

```
SECRET_KEY=
SEED_ADMIN_PASSWORD=
SEED_MECHANIC_PASSWORD=
SEED_ACCOUNTANT_PASSWORD=
```

`DATABASE_URL` — из PostgreSQL plugin, руками не дублировать схему, если Railway уже подставил.

Опционально: `PROXY_API_URL`, `PROXY_API_TOKEN`, `ERP_SYNC_*`.

## Команда запуска

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Отладка

Логи в Railway Dashboard. Локально:

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8035
```

`GET http://127.0.0.1:8035/health` → `"app": "Service Center ERP"`.

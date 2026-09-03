# Деплой на Railway

Образец: [stock-safety-monitor](https://github.com/IvanBondarenkoIT/stock-safety-monitor) → Railway.  
Отличия: это **web** (uvicorn), не cron; нужен **PostgreSQL**.

Публичный репозиторий: [IvanBondarenkoIT/service-center-erp](https://github.com/IvanBondarenkoIT/service-center-erp).

## Чеклист

- [ ] Код в GitHub, Railway: New Project → этот репозиторий → Dockerfile
- [ ] **Root Directory** пустой (корень репо, не `apps/service-center-erp`)
- [ ] В Settings сервиса **Cron Schedule пустой** (long-running web, не job)
- [ ] **PostgreSQL** в том же проекте и **привязан к web-сервису** (иначе будет `localhost:5433`)
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

`DATABASE_URL` должен указывать на Postgres **внутри Railway**, не на `localhost:5433`.

1. New → Database → PostgreSQL (тот же проект, что и web).
2. Сначала откройте карточку **Postgres → Variables** и посмотрите точные имена.
   Обычно есть `DATABASE_URL` (внутренний, `.railway.internal`). `DATABASE_PRIVATE_URL` есть не всегда — если его нет, reference станет пустой строкой и приложение упадёт.
3. Web-сервис → Variables → Add Variable Reference (лучше выбрать из списка, не печатать руками):
   `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
4. Если plugin уже добавил `DATABASE_URL` / `PGHOST` — руками не копируйте локальный URL.
5. Redeploy web. В логах не должно быть `localhost` / `5433` и пустого URL.

Опционально: `PROXY_API_URL`, `PROXY_API_TOKEN`, `ERP_SYNC_*`.

## Порт (Railway)

Публичный URL ходит на **`$PORT`**, который задаёт Railway (часто **8080**, не всегда). Локально приложение слушает **8035**.

В логах должно быть `Uvicorn running on http://0.0.0.0:<тот же PORT>`. Если видите `8035`, а снаружи «Application failed to respond» — прокси стучится в другой порт.

- **Не** добавляйте `PORT=8035` (и вообще `PORT`) в Variables сервиса — Railway сам подставляет свой.
- Settings → **Custom Start Command** либо пустой (тогда Dockerfile: `--port ${PORT}`), либо `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Не хардкодьте `8035`.
- Networking / Target Port не ставьте вручную на 8035.

## Команда запуска

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Отладка

Логи в Railway Dashboard.

**`Could not parse SQLAlchemy URL from string ''`** — переменная `DATABASE_URL` есть, но пустая. Обычно `${{Postgres.DATABASE_PRIVATE_URL}}` не существует. Откройте Postgres → Variables и поставьте `${{Postgres.DATABASE_URL}}`.

**`Application failed to respond` + uvicorn на `:8035`** — приложение слушает локальный порт, Railway проксирует `$PORT` (часто 8080). Уберите `PORT` из Variables, Start Command с `$PORT`, задеплойте коммит где Dockerfile использует `${PORT}`.

**`connection to server at "localhost" … port 5433` / `Connection refused`** — у web-сервиса нет URL облачной БД. Postgres не добавлен или не linked. Не вставляйте строку из `.env` с `localhost:5433`.

Локально:

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8035
```

`GET http://127.0.0.1:8035/health` → `"app": "Service Center ERP"`.

# Этап 0. Скрипт скриншотов и сверка контракта

Ветка: `feature/mobile-0-baseline`. UI в этом этапе не меняется.

## Задача

1. **Сверка контракта.** Пройди `static/app.js` и `static/intake-scan.js` целиком и сверь с разделом 2 `RULES.md`
   все селекторы (id, классы, data-атрибуты, name полей), на которые опирается JS, и все `hx-*` в `templates/`.
   Если чего-то не хватает — допиши в `RULES.md`; если лишнее — оставь, но отметь в отчёте. Других правок в `RULES.md` не делай.

2. **Скрипт `scripts/ui_snapshots.py`** (Playwright, Chromium):
   - поднимает приложение (uvicorn в фоне на свободном порту) на отдельной SQLite-базе во временной папке
     (не `scerp_local.db`, не трогать `.env`), `SECRET_KEY` и пароли seed — дефолтные для локального режима;
   - наполняет демо-данными через те же POST-формы, что в `tests/` (см. `tests/test_stage3_orders.py::_payload`,
     `tests/test_stage4_cash.py`): ~10 заказов разных статусов и всех трёх центров, заказ с 3 строками разных типов
     и способов оплаты, гарантийная строка с EUR, заказ «без SN», 3–4 оплаченных (выданных), расход и инкассация в кассе;
     данные детерминированные (фиксированный seed), чтобы скриншоты сравнивались;
   - логинится admin / mechanic_batumi / accountant и снимает full-page скриншоты всех страниц, доступных роли:
     login, `/`, `/orders/intake`, `/orders/new`, заказ в работе, выданный заказ, `/cash`, `/cash/entries`,
     формы редактирования кассы, `/reports`, `/more`, все `/dict/*`, все `/admin/*` (включая `/admin/users/<id>`);
   - два размера: 390×844 (`is_mobile=True`, `has_touch=True`, `device_scale_factor=2`) и 1366×900;
   - опционально `--locale ka` (переключает язык через POST `/locale`) — для проверки грузинского;
   - для каждой страницы пишет в `report.json`: `scrollWidth` vs `innerWidth`; список интерактивных элементов
     (a, button, input, select, textarea, label с чекбоксом) высотой < 44 px; число полей с font-size < 16 px;
     ошибки консоли и упавшие запросы;
   - сохраняет всё в `artifacts/ui/<name>/` (`--name`, по умолчанию имя текущей git-ветки); добавь `artifacts/` в `.gitignore`;
   - `--compare <другой прогон>` собирает `artifacts/ui/<name>/compare.html`: по каждой странице и размеру
     «до» и «после» рядом + таблица метрик до/после с подсветкой ухудшений;
   - зависимости (`playwright`) — в новый `requirements-dev.txt`, не в `requirements.txt` (в Docker-образ не попадает);
     в начале скрипта понятная ошибка, если Playwright/Chromium не установлены, с командой установки.

3. Прогони `python scripts/ui_snapshots.py --name baseline` и `pytest -q`.

4. В `README.md` проекта добавь раздел «UI-скриншоты» в 3–5 строк (установка dev-зависимостей, запуск, compare).

## Отчёт

`docs/mobile-first/reports/stage-0.md` по шаблону. В разделе «Проверки» — сводка `report.json` baseline по всем
страницам на 390 px (таблица: страница, scrollWidth, полей < 16px, элементов < 44px, ошибки консоли).
Сравни с `AUDIT.md`: совпадают ли цифры, что нашлось нового.

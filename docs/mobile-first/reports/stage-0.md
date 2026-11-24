# Отчёт: этап 0 — скрипт скриншотов и сверка контракта

- Ветка: `feature/mobile-0-baseline`
- Коммит: `91077f2`
- Дата: 2026-11-24
- Итог: готово к ревью (после rework по `reviews/stage-0.md`)

## Что сделано

1. **Сверка контракта.** Пройдены `static/app.js` и `static/intake-scan.js`, сверено с §2 `RULES.md` и `hx-*` в `templates/`.
   В `RULES.md` добавлено: id `scan-file-fallback`; поля кассы `kind` / `subtype`; уточнены HTMX-цели.
2. **`scripts/ui_snapshots.py`:** uvicorn + SQLite, демо через POST-формы, скрины 390×844 и 1366×900,
   `report.json`, `--compare` → `compare.html`. `requirements-dev.txt`, `artifacts/` в `.gitignore`.
3. Прогоны: `pytest -q`, `python scripts/ui_snapshots.py --name baseline --keep-db`.
4. README — раздел «UI-скриншоты».

### Rework по `reviews/stage-0.md`

1. `smallFontFields`: исключены `type=hidden`, невидимые (`getClientRects`, `display/visibility` у предков).
2. Метрика `clipped` / `clippedCount` (+ sample): `overflow-x` hidden/clip/auto/scroll с `scrollWidth > clientWidth`,
   и элементы с правым краем за вьюпортом (не `position: fixed`). Колонка в `compare.html`, рост = worse.
3. `order_in_progress` снимает заказ `multi` (`/orders/{multi}`), не однострочный #1.
4. Лог uvicorn → `artifacts/ui/<name>/server.log` (не PIPE).
5. Второй снимок `__viewport.png` (без `full_page`); в compare — full + viewport.
6. В STATUS/отчёте — SHA реального tip ветки.

## Изменённые файлы

```text
.gitignore
README.md
docs/mobile-first/RULES.md
docs/mobile-first/STATUS.md
docs/mobile-first/reports/stage-0.md
docs/mobile-first/reviews/stage-0.md
requirements-dev.txt
scripts/ui_snapshots.py
```

## Проверки

- `pytest -q`: **133 passed, 1 skipped**
- Скриншоты: `python scripts/ui_snapshots.py --name baseline --keep-db`
  → `artifacts/ui/baseline/report.json` (72 страницы), `server.log`, full + viewport PNG
- Метрики 390 px (admin). `scrollWidth` vs viewportWidth=390.

| Страница | scrollWidth | Полей &lt; 16px | Tap &lt; 44 | clipped | overflow |
|----------|------------:|----------------:|------------:|--------:|:--------:|
| `/login` | 390 | 2 | 3 | 0 | no |
| `/` | 390 | 1 | 10 | 0 | no |
| `/orders/intake` | 390 | 4 | 5 | 0 | no |
| `/orders/new` → intake | 390 | 4 | 5 | 0 | no |
| `/orders/{multi}` in_progress | 448 | 17 | 29 | 7 | yes |
| `/orders/{id}` issued | 417 | 12 | 16 | 5 | yes |
| `/cash` | 390 | 3 | 15 | 26 | no |
| `/cash/entries` | 390 | 8 | 15 | 0 | no |
| `/cash/entries/{id}/edit` | 390 | 4 | 7 | 0 | no |
| `/cash/openings/{id}/edit` | 390 | 4 | 7 | 0 | no |
| `/reports` | 390 | 3 | 4 | 0 | no |
| `/more` | 390 | 0 | 4 | 0 | no |
| `/dict/clients` | 390 | 29 | 33 | 0 | no |
| `/dict/machines` | 390 | 43 | 47 | 1 | no |
| `/dict/reasons` | 390 | 9 | 13 | 0 | no |
| `/dict/erp-catalog` | 390 | 2 | 5 | 0 | no |
| `/admin/users` | 519 | 5 | 11 | 11 | yes |
| `/admin/users/1` | 390 | 5 | 8 | 0 | no |
| `/admin/audit` | 394 | 0 | 13 | 7 | yes |
| `/admin/order-history` | 496 | 4 | 21 | 9 | yes |
| `/admin/prices` | 390 | 5 | 7 | 0 | no |

На `/cash` `clipped=26` при `scrollWidth=390` — таблицы «Приход» / сверка обрезаны внутри (`overflow-x:auto`, content~493–510).
`order_in_progress` = заказ #8 (`SN-UI-MULTI`, 3 строки); viewport-снимок — первый экран без липкого шума full-page.

### Сверка с AUDIT.md

| Тема | AUDIT | baseline (после rework) |
|------|-------|-------------------------|
| Login поля &lt;16 | — | 2 (было ложно 8) |
| Форма заказа поля &lt;16 | ~16 | 17 (видимые; multi-line) |
| `/dict/machines` | 31 | 43 (больше карточек в демо) |
| `/cash` обрезка таблицы | да | `clipped=26`, scrollWidth страницы 390 |
| `/admin/users` scroll | 539 | 519 + clipped 11 |

## Изменения в тестах

нет

## Отклонения от RULES.md

нет

## Что проверить руками на телефоне

- Скрины `artifacts/ui/baseline/shots/admin__mobile__order_in_progress*.png` — три строки / multi.
- `admin__mobile__cash*.png` — обрезка «Приход» отражена в `clipped`.

## Не проверено

- Реальный телефон, камера, `--locale ka`, печать.

## Найдено вне этапа

- `window.innerWidth` при `is_mobile` растёт с документом — overflow меряем по configured width.
- Full-page sticky Save/nav — шум; для сравнения важнее `__viewport`.

## Вопросы

нет

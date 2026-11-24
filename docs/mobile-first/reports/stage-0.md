# Отчёт: этап 0 — скрипт скриншотов и сверка контракта

- Ветка: `feature/mobile-0-baseline`
- Коммит: `7eaa1ae`
- Дата: 2026-11-24
- Итог: готово к ревью

## Что сделано

1. **Сверка контракта.** Пройдены `static/app.js` и `static/intake-scan.js`, сверено с §2 `RULES.md` и `hx-*` в `templates/`.
   В `RULES.md` добавлено: id `scan-file-fallback`; поля кассы `kind` / `subtype`; уточнены HTMX-цели
   `#history-box`, `#client-history-box`, `#erp-model-suggest`, `#lines-body`.
2. **`scripts/ui_snapshots.py`:** uvicorn на свободном порту + временная SQLite (или `--keep-db` под `artifacts/ui/<name>/`),
   демо через POST-формы как в тестах, скрины admin / mechanic_batumi / accountant на 390×844 и 1366×900,
   `report.json`, `--compare` → `compare.html`. Зависимости: `requirements-dev.txt`. `artifacts/` в `.gitignore`.
3. Прогоны: `pytest -q`, `python scripts/ui_snapshots.py --name baseline --keep-db`.
4. В корневом `README.md` — раздел «UI-скриншоты».

## Изменённые файлы

```text
.gitignore
README.md
docs/mobile-first/RULES.md
docs/mobile-first/STATUS.md
docs/mobile-first/reports/stage-0.md
requirements-dev.txt
scripts/ui_snapshots.py
```

## Проверки

- `pytest -q`: **133 passed, 1 skipped**
- Скриншоты: `python scripts/ui_snapshots.py --name baseline --keep-db`
  → `artifacts/ui/baseline/report.json` (72 страницы: 3 роли × (login + экраны) × 2 размера)
- Compare smoke: `python scripts/ui_snapshots.py --name baseline-compare-smoke --compare baseline`
  → `artifacts/ui/baseline-compare-smoke/compare.html`
- Метрики 390 px (viewportWidth=390; роль admin, кроме login — все роли одинаковы на login).
  `scrollWidth` сравнивается с **заданной** шириной вьюпорта (не с `window.innerWidth`, который раздувается вместе с документом).

| Страница | scrollWidth | Полей &lt; 16px | Элементов &lt; 44px | overflow | console |
|----------|------------:|----------------:|--------------------:|:--------:|--------:|
| `/login` | 390 | 8 | 3 | no | 0 |
| `/` | 390 | 8 | 10 | no | 0 |
| `/orders/intake` | 390 | 11 | 5 | no | 0 |
| `/orders/new` → intake | 390 | 11 | 5 | no | 0 |
| `/orders/{id}` in_progress | 408 | 29 | 18 | yes | 0 |
| `/orders/{id}` issued | 417 | 29 | 16 | yes | 0 |
| `/cash` | 390 | 9 | 15 | no | 0 |
| `/cash/entries` | 390 | 16 | 15 | no | 0 |
| `/cash/entries/{id}/edit` | 390 | 12 | 7 | no | 0 |
| `/cash/openings/{id}/edit` | 390 | 10 | 7 | no | 0 |
| `/reports` | 390 | 9 | 4 | no | 0 |
| `/more` | 390 | 6 | 4 | no | 0 |
| `/dict/clients` | 390 | 35 | 33 | no | 0 |
| `/dict/machines` | 390 | 49 | 47 | no | 0 |
| `/dict/reasons` | 390 | 15 | 13 | no | 0 |
| `/dict/erp-catalog` | 390 | 10 | 5 | no | 0 |
| `/admin/users` | 519 | 11 | 11 | yes | 0 |
| `/admin/users/1` | 390 | 11 | 8 | no | 0 |
| `/admin/audit` | 394 | 6 | 13 | yes | 0 |
| `/admin/order-history` | 496 | 10 | 21 | yes | 0 |
| `/admin/prices` | 390 | 11 | 7 | no | 0 |

Мобильный overflow также у mechanic: `order_*`, `cash_entries`, `cash_entry_edit`; у accountant: `admin_order_history`.

- Десктоп 1366 px: без изменений UI (этап 0 не трогал CSS); скрины сняты для регрессии.

### Сверка с AUDIT.md

| Тема | AUDIT | baseline | Комментарий |
|------|-------|----------|-------------|
| Форма заказа, поля &lt;16 | ~16 | 29 | Считаем все `input/select/textarea`, включая hidden у чипов — цифра выше аудита. |
| `/dict/machines` поля &lt;16 | 31 | 49 | Больше карточек/форм в демо-данных. |
| `/dict/clients` поля &lt;16 | 21 | 35 | То же. |
| `/admin/users` scroll | 539 | 519 | Совпадает по сути (гор. скролл таблицы). |
| `/admin/order-history` scroll | 427 | 496 | Гор. скролл подтверждён. |
| `/cash` таблица 596 | — | scrollWidth=390 | Таблица обрезана/внутри контейнера; `document.scrollWidth` не ловит внутренний overflow без видимого скролла страницы — как в аудите «обрезана без видимого скролла». |
| Заказ height ~4300 | — | full-page shot | Высота не в метриках; на скрине длинная форма + сырая история. |
| Новое относительно AUDIT | — | overflow на форме заказа 408–417; audit/order-history; mechanic cash edit | Зафиксировано в `report.json`. |

## Изменения в тестах

нет

## Отклонения от RULES.md

нет (UI/`app/` не менялись; только дополнение §2 RULES по сверке)

## Что проверить руками на телефоне

- Не требуется для этапа 0 (скрипт и контракт). Имеет смысл открыть `artifacts/ui/baseline/shots/` и пробежаться глазами по admin mobile order/cash/users.

## Не проверено

- Реальный телефон, камера/сканер, язык `ka` полный прогон (`--locale ka` поддерживается, не гонялся в этом отчёте), `@media print`.

## Найдено вне этапа

- Логин через `page.fill` + submit в headless Playwright не сохранял cookie; скрипт логинится через `context.request.post` (cookie jar контекста).
- `window.innerWidth` при `is_mobile=True` растёт вместе с широким документом — для overflow нужна ширина из конфига вьюпорта.

## Вопросы

нет

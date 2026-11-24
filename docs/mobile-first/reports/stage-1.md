# Отчёт: этап 1 — фундамент

- Ветка: `feature/mobile-1-foundation`
- Коммит: _(tip)_
- Дата: 2026-11-24
- Итог: готово к ревью

## Что сделано

1. **CDN убраны.** `static/vendor/htmx/htmx.min.js`, `html5-qrcode`, шрифты IBM Plex Sans/Mono + Noto Sans Georgian (woff2 latin/cyrillic/georgian), OFL рядом. Иконки — макрос `templates/partials/icon.html` (`assignment`, `qr_code_scanner`, `payments`, `menu`, `search`, `photo_camera`, `delete`, `shopping_bag`). В `base.html` / `login.html` нет googleapis/unpkg.
2. **Поля.** Селектор `input:not([type])`, `search`, `email`; явные `type` в справочниках/админке. На телефоне `font-size: 16px` у полей; с `min-width: 600px` — 14px. Высота ≥ `--tap` (44px).
3. **Клавиатуры.** `inputmode="decimal"` на суммах; SN — `autocapitalize/autocorrect/spellcheck`; поиск — `type=search` + `enterkeyhint`; телефон — `autocomplete=tel`.
4. **Тап-зоны.** Чипы, язык, чекбоксы, icon-btn, ghost — `min-height: var(--tap)`.
5. **Safe-area.** `viewport-fit=cover`; bottom-nav и sticky save с `env(safe-area-inset-bottom)`; отступ `main` учитывает меню.
6. **PWA.** `theme-color`, `static/manifest.webmanifest` (иконки 192/512), без service worker.
7. **CSS.** Брейкпоинты только `min-width: 600/900/1200`; переменные `--tap`, `--nav-h`, `--bar-h`, `--space-*`.
8. **clipped.** Только самый внешний элемент; `.hscroll` исключён (класс в CSS + RULES + ряды чипов). Baseline снят в worktree от `feature/mobile-0-baseline` с той же метрикой.

## Изменённые файлы

```text
docs/mobile-first/RULES.md
docs/mobile-first/STATUS.md
docs/mobile-first/reports/stage-1.md
scripts/ui_snapshots.py
static/app.css
static/manifest.webmanifest
static/vendor/** (htmx, fonts, html5-qrcode)
templates/base.html
templates/login.html
templates/partials/icon.html
templates/orders/* (form, list, intake, _line_row, _history_client)
templates/cash/*
templates/dictionaries/*
templates/admin/*
```

## Проверки

- `pytest -q`: **133 passed, 1 skipped**
- `python scripts/ui_snapshots.py --name stage1 --compare baseline`
  → `artifacts/ui/stage1/compare.html`
- Цель **полей &lt; 16 px = 0** на всех страницах 390 px — **достигнута**
- Внешние failed requests: **0** (htmx/fonts/icons локально)
- Метрики admin @ 390 (baseline → stage1):

| Страница | font до→после | tap до→после | clipped до→после |
|----------|---------------|--------------|------------------|
| login | 2→0 | 3→0 | 0→0 |
| home | 1→0 | 10→1 | 0→0 |
| intake | 4→0 | 5→1 | 0→0 |
| order_in_progress | 16→0 | 29→1 | 2→2 |
| order_issued | 11→0 | 16→2 | 2→2 |
| cash | 3→0 | 15→5 | 2→2 |
| cash_entries | 7→0 | 15→1 | 0→0 |
| dict_machines | 43→0 | 47→1 | 1→0 |
| dict_clients | 29→0 | 33→1 | 0→0 |
| admin_users | 5→0 | 11→5 | 2→2 |
| admin_order_history | 4→0 | 21→17 | 2→2 |

(В метрике font пропущены `checkbox/radio/button/…` — не текстовые поля; iOS-zoom цель про текстовый ввод.)

- Десктоп 1366: поля в справочниках стилизованы; раскладка не менялась по смыслу этапа.

## Изменения в тестах

нет

## Отклонения от RULES.md

нет (бэкенд не трогали)

## Что проверить руками на телефоне

- Нет вспышки текста иконок / FOIT шрифтов при медленной сети (airplane → Wi‑Fi).
- Фокус в поле суммы/телефона — без зума iOS.
- Чипы оплаты скроллятся в `.hscroll` без полосы прокрутки.
- Нижнее меню и «Сохранить» не перекрывают контент на iPhone с home indicator.

## Не проверено

- Реальный телефон, камера сканера, `--locale ka`, печать.

## Найдено вне этапа

- Таблицы кассы/истории всё ещё `clipped` (этапы 4/6).
- Часть tap &lt; 44 остаётся (ссылки в таблицах) — этапы списка/админки.

## Вопросы

нет

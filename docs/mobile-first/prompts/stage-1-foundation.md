# Этап 1. Фундамент

Ветка: `feature/mobile-1-foundation`. Файлы: `templates/base.html`, `static/`, атрибуты полей в шаблонах.
Раскладку экранов в этом этапе не меняем.

## Задача

1. **Без внешних CDN.** Скачай в `static/vendor/`: htmx 2.0.4; шрифты IBM Plex Sans/Mono и Noto Sans Georgian
   (woff2, только используемые начертания, наборы latin, cyrillic, georgian), `@font-face` с `font-display: swap`.
   Иконки: найди все `material-symbols-outlined` в шаблонах и JS и замени на инлайн-SVG через Jinja-макрос
   `templates/partials/icon.html` (`{{ icon('search') }}` и т.п., размер через `currentColor`/`1em`), чтобы при
   медленной сети не появлялись слова вроде `qr_code_scanner`. Если JS вставляет иконку текстом — переделай на SVG.
   В `base.html` убери fonts.googleapis.com, fonts.gstatic.com и unpkg.com; локальные файлы с `?v={{ asset_v }}`.
   Лицензии шрифтов (OFL) положи рядом.
2. **Поля.** Стили должны применяться и к `input` без `type`: добавь `input:not([type])`, `type=search`, `type=email`
   в селектор, а в шаблонах проставь явный `type`. На телефоне `font-size` у `input`, `select`, `textarea` ≥ 16 px
   (на десктопе можно оставить текущий). Высота полей и кнопок ≥ 44 px.
3. **Клавиатуры.** Суммы — `inputmode="decimal"` (`type=number` оставить, если на него опираются JS или тесты).
   Серийники — `autocapitalize="characters" autocorrect="off" spellcheck="false"`. Поиск — `type="search" enterkeyhint="search"`.
   Телефон — `autocomplete="tel"`.
4. **Тап-зоны.** `button.chip`, переключатель языка, чекбоксы с лейблом, ссылки-действия: ≥ 44 px по высоте на телефоне
   (`min-height`/`padding`, визуально не раздувая).
5. **Safe-area.** `viewport-fit=cover` в meta viewport; нижнее меню и липкие панели — `padding-bottom: env(safe-area-inset-bottom)`;
   у `main` нижний отступ = высота меню + липкой панели, чтобы контент не прятался.
6. **PWA-минимум.** `<meta name="theme-color">` в цвет бренда, `static/manifest.webmanifest` (имя, иконки 192/512 из static,
   `display: standalone`, `start_url: /`). Service worker **не** добавлять.
7. **CSS.** Сведи брейкпоинты `app.css` к `min-width: 600/900/1200px` (сейчас `max-width: 800`, `max-width: 899`,
   `min-width: 700/900/1200`) без изменения вида на 390 и 1366 px. Вынеси цвета, отступы, радиусы, высоты
   (`--tap: 44px`, `--bar-h`, `--nav-h` и т.п.) в CSS-переменные `:root`.

8. **Доработка метрики `clipped` (из ревью этапа 0).** Сейчас считаются и все потомки широкого элемента
   (на `/cash` 26 = таблица + thead + tr + th + td…). Считай только самый внешний: пропускай элемент, если его предок
   уже попал в `clipped`. Намеренные горизонтальные скроллеры (ряды чипов, фильтры статусов) помечай классом `.hscroll`
   (`overflow-x: auto`, `scroll-snap`, без видимого скроллбара) — сам контейнер и его потомки в `clipped` не считаются.
   Добавь `.hscroll` в `app.css` и в раздел 3 `RULES.md`. Перегенерируй `baseline` на `main` до своих правок
   (или прогони скрипт с этой метрикой на коммите `main` через `git worktree`), чтобы сравнение было честным.

## Проверки

`pytest -q`; `python scripts/ui_snapshots.py --name stage1 --compare baseline`.
Цель: полей < 16 px = 0 на всех страницах 390 px; на 1366 px визуально без изменений, кроме починенных полей в справочниках;
в `report.json` нет запросов к внешним доменам.

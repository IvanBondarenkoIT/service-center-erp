# Правила mobile-first (обязательны для всех этапов)

## 1. Что нельзя менять

- URL, методы и `action` форм, `formaction`.
- Атрибуты `name`, `id`, `value` у полей и кнопок, все `data-*` и `hx-*` атрибуты.
- Роутеры, модели, сервисы в `app/` (`app/routers`, `app/models.py`, `app/services`, `app/deps.py`).
  Разрешено: `app/i18n/*.json`; единственное заранее согласованное исключение — доступ к `GET /more` на этапе 2.
  Любая другая правка бэкенда — только после вопроса Ивану (статус `blocked`).
- Хранимый формат данных (события заказа, аудит) — меняем только отображение.
- Печать кассы (`@media print`) и выгрузка Excel должны выглядеть как до правок.

Переносить элементы в разметке можно, удалять или переименовывать то, что выше, — нельзя.
Если кнопка переезжает в другое место (например, в липкую панель вне `<form>`), используй атрибут `form="<id формы>"`,
а не дубликат кнопки.

## 2. Контракт с JavaScript

`static/app.js` и `static/intake-scan.js` опираются на эти селекторы. Они должны остаться в разметке с тем же смыслом.
Список снят 24.11.2026 с коммита `6d1d11b`; на этапе 0 Cursor сверяет его с кодом и дополняет.

**id:** `lines-body`, `new_machine_serial`, `new_machine_model`, `new_client_phone`, `new_client_name`, `no_machine`,
`erp_goods_id`, `erp-model-suggest`, `collection-subtype`, `scan-camera-btn`, `scan-file-input`, `scan-status`,
`scan-hint`, `scan-failed`, `scan-file-fallback` (контейнер Html5Qrcode), а также цели HTMX `history-box`,
`client-history-box`.

**Классы:** `.chip-row`, `.chip-row[data-toggle]`, `button.chip`, `.chip-line-warranty`, `.line-pay-row`,
`.line-amount-wrap`, `.line-val-wrap`, `.line-part-suggest`, `.is-locked`.
JS сам переключает классы `active`, `is-busy`, `is-warranty`, `is-warranty-pay` — их стили можно менять, имена нельзя.

**data-атрибуты:** `data-line-card`, `data-input`, `data-toggle`, `data-value`, `data-erp-id`, `data-erp-name`,
`data-part-id`, `data-part-name`, `data-fill-name`, `data-client`, `data-kind`, `data-model-name`, `data-msg`,
`data-name`, `data-val`, `data-diagnostic-label`, `data-diagnostic-price`.

**Поля по name внутри карточки строки:** `line_type`, `description`, `part_code`, `payment_type`, `is_warranty`,
`amount`, `warranty_eur`, `promo_id`.

**Поля/чипы вне строки заказа (кассa):** `name="kind"` (расход/инкасация) управляет видимостью `#collection-subtype`;
`name="subtype"` — подтип инкасации через те же `.chip-row` / `data-value`.

**HTMX:** эндпоинты `/dict/erp-suggest`, `/dict/part-suggest`, `/orders/partials/history`,
`/orders/partials/history-by-client`, `/orders/partials/line-row`; `hx-include="closest [data-line-card]"`,
`hx-target="next .line-part-suggest"` — значит, `.line-part-suggest` должен оставаться **следующим соседом**
поля, на котором висит этот `hx-target`. На форме заказа также: `hx-target="#history-box"`,
`#client-history-box`, `#erp-model-suggest`, `#lines-body` (добавление строки, `hx-swap="beforeend"`).

## 3. CSS

- Mobile-first: базовые стили — для телефона; расширения только `@media (min-width: 600px | 900px | 1200px)`.
  Новых `max-width` медиазапросов не добавлять (кроме `@media print`).
- Цвета, отступы, радиусы, высоты — через CSS-переменные в `:root` (`--tap`, `--nav-h`, `--bar-h`, …).
- На 390 px нет горизонтального скролла страницы. Широкие таблицы — паттерн `.table-cards` (этап 6).
  Намеренный горизонтальный скролл (ряды чипов, фильтры) — только в контейнере с классом `.hscroll`
  (`overflow-x: auto`, scroll-snap, без видимого скроллбара). Метрика `clipped` в `ui_snapshots.py`
  пропускает `.hscroll` и потомков; считает только самый внешний обрезанный элемент.
- Тап-зоны ≥ 44×44 px. Шрифт `input`, `select`, `textarea` ≥ 16 px на телефоне.
- Липкие панели и нижнее меню учитывают `env(safe-area-inset-bottom)`; контент под ними не прячется.
- Десктоп (≥ 900 px) не должен стать хуже.

## 4. Тексты и языки

- Все видимые тексты — через `t()` и `app/i18n/{ru,en,ka}.json`. Новый ключ добавляется во все три файла.
- Грузинские слова длиннее: проверять, что подписи (особенно нижнего меню и чипов) не ломают раскладку на `ka`.

## 5. Тесты

- `pytest -q` должен быть зелёным в конце каждого этапа.
- Если тест падает из-за изменившейся разметки или текста — не правь его молча. Опиши в отчёте: какой тест,
  что проверял, почему изменение UI правильное, как поправлен тест. Тесты на бизнес-логику (суммы, касса, права) не менять.
- Тексты, на которые есть тесты (например, `SN: —` в списке заказов), сохранять.

## 6. Git

- Одна ветка на этап, от актуального `main`. Имя — в промпте этапа.
- Коммиты небольшие, понятные сообщения.
- В `main` не мержить и `main` не пушить: мерж = выкладка на прод.
- `artifacts/` (скриншоты) не коммитить.

# Статус этапов

Статусы: `todo` · `in_progress` · `review` · `rework` · `blocked` · `done`. Порядок работы — в `README.md`.

| # | Этап | Промпт | Ветка | Статус | Обновлено | Последний коммит | Отчёт | Ревью |
|---|------|--------|-------|--------|-----------|------------------|-------|-------|
| 0 | Скрипт скриншотов, сверка контракта | [stage-0](prompts/stage-0-baseline.md) | feature/mobile-0-baseline | review | 2026-11-24 | 91077f2 | [stage-0.md](reports/stage-0.md) | [stage-0.md](reviews/stage-0.md) |
| 1 | Фундамент: шрифты/иконки локально, поля 16px, тап-зоны, safe-area | [stage-1](prompts/stage-1-foundation.md) | feature/mobile-1-foundation | todo | | | | |
| 2 | Каркас: плашка, нижнее меню по ролям, «Ещё» | [stage-2](prompts/stage-2-shell.md) | feature/mobile-2-shell | todo | | | | |
| 3 | Приёмка | [stage-3](prompts/stage-3-intake.md) | feature/mobile-3-intake | todo | | | | |
| 4 | Форма заказа | [stage-4](prompts/stage-4-order-form.md) | feature/mobile-4-order-form | todo | | | | |
| 5 | Список заказов | [stage-5](prompts/stage-5-orders-list.md) | feature/mobile-5-orders-list | todo | | | | |
| 6 | Касса | [stage-6](prompts/stage-6-cash.md) | feature/mobile-6-cash | todo | | | | |
| 7 | Админка и справочники, итоговая проверка | [stage-7](prompts/stage-7-admin.md) | feature/mobile-7-admin | todo | | | | |

Этапы 0 → 1 → 2 строго по порядку. 3–7 можно переставлять, но каждый начинается от `main` с уже смерженными предыдущими.

## Заметки

<!-- Cursor и Claude добавляют сюда короткие заметки, которые касаются нескольких этапов. Новые сверху. -->

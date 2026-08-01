## 1. Activity list scoping

- [x] 1.1 Add class `tasks-activity-list` beside `memory-list` on `#tasks-activity-list` in `static/js/tasks.js` (`_renderActivityView`)
- [x] 1.2 Add `#tasks-activity-list.tasks-activity-list` (or `.tasks-activity-list`) rule with `gap: 8px` in `static/style.css`

## 2. Task-log card CSS

- [x] 2.1 Add `.task-log-row` card chrome (flex column, padding, border, radius, background, `flex-shrink: 0`, left accent from `--cat-hue`) near Tasks/Memory styles in `static/style.css`
- [x] 2.2 Style `.task-log-row-head`, `.task-log-name`, `.task-log-time`, `.task-log-status*`, `.task-log-task-icon`, `.task-log-repeat`, `.task-log-account-tag`
- [x] 2.3 Style `.task-log-row-body` and `.task-log-row-actions` (spacing so body/actions stay inside the card); style action buttons compactly
- [x] 2.4 Style `.task-log-row.is-skipped` (slim, dimmed) and `.is-long:not(.expanded) .task-log-row-body` clamp + `.expanded` reveal
- [x] 2.5 Add minimal running/queued chrome (`.is-running`, `.task-log-running-inline`) so live rows remain readable inside cards

## 3. Verify

- [x] 3.1 Manual smoke: Tasks → Activity — consecutive entries clearly separated as cards
- [x] 3.2 Manual smoke: skipped rows stay compact; long rows collapse/expand; Copy log / Run again still work

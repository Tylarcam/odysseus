## Why

The Tasks modal Activity tab renders each run as a `.task-log-row`, but those classes have no CSS in `static/style.css`. Entries collapse into one continuous text stream with no gap, border, or accent — operators cannot tell where one run ends and the next begins.

## What Changes

- Add card-style CSS for `.task-log-*` Activity rows (border, padding, background, left accent via `--cat-hue`, list gap).
- Style head / body / actions hierarchy, skipped slim rows, and collapsed long bodies (`.is-long` / `.expanded`).
- Optionally add a scoped class on `#tasks-activity-list` so Activity can use a larger gap than Memory’s `.memory-list` default without affecting other lists.

## Capabilities

### New Capabilities
- `tasks-activity-ui`: Visual separation and hierarchy for Tasks Activity log entries (card chrome, gap, skip/expand presentation).

### Modified Capabilities
- (none — `openspec/specs/` has no existing Tasks Activity capability)

## Impact

- `static/style.css` — primary: new `.task-log-*` and Activity-list gap rules near existing Tasks/Memory styles
- `static/js/tasks.js` — optional one-line class on `#tasks-activity-list` for scoped gap
- No API, stacking/filter, or per-task run-history (`.task-run-item`) changes
- Verification: manual smoke in Tasks → Activity

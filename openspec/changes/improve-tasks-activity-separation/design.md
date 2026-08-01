## Context

Activity entries are built in `static/js/tasks.js` (`_renderActivityEntry`) as `.task-log-row` blocks with `--cat-hue`, head/body/actions, and state classes (`.is-skipped`, `.is-long`, `.is-running`, `.expanded`). The list lives in `#tasks-activity-list` with class `memory-list` (`gap: 4px`). Markup and expand/action wiring already exist; **no `.task-log-*` rules are present in `static/style.css`**, so rows have no visual boundary.

## Goals / Non-Goals

**Goals:**
- Make each Activity run read as a distinct card (gap, border, padding, subtle background).
- Use `--cat-hue` for a left accent stripe so category color already computed in JS becomes visible.
- Keep skipped rows slim/dimmed and long bodies collapsed until expanded.
- Match existing `.memory-item` token language (`var(--border)`, `color-mix`, 8px radius).

**Non-Goals:**
- Changing stacking, filters, chips, or `/api/tasks/runs/recent`.
- Restyling per-task run history (`.task-run-item`).
- Broader Tasks modal redesign or new JS behavior beyond an optional list class for gap.

## Decisions

**Card chrome over hairline dividers or zebra striping.**
Dividers alone fail when bodies are multi-paragraph; zebra fights category accent hue. Cards match Memory list items the operator already knows. Alternative considered: divider + spacing only — rejected because head/body/actions still bleed together without a shared container background.

**CSS-first; minimal JS.**
All separation is stylesheet. Add class `tasks-activity-list` on `#tasks-activity-list` so Activity can set `gap: 8px` without changing Memory’s global `.memory-list { gap: 4px }`. No rewrite of `_renderActivityEntry` HTML.

**Left accent from `--cat-hue`.**
JS already sets `style="--cat-hue:N;"`. Use `border-left: 3px solid hsl(var(--cat-hue), 55%, 45%)` (or equivalent that works in light/dark via existing theme vars). Alternative: full colored background wash — rejected as too loud next to dense log text.

**Long-body collapse via existing classes.**
`.is-long:not(.expanded) .task-log-row-body` gets `max-height` + `overflow: hidden`; `.expanded` removes the clamp. Toggle wiring already exists in `_wireActivityRows`.

**Place rules near Tasks/Memory (~11340+).**
Keeps discovery next to `.memory-list` / `.task-status-badge` rather than a distant orphan block.

## Risks / Trade-offs

- **[Risk] Dark/light theme contrast on accent** → **Mitigation**: use moderate saturation/lightness; fall back to `var(--border)` if `--cat-hue` missing.
- **[Risk] Collapsed max-height cuts mid-line awkwardly** → **Mitigation**: keep existing “Show more” control; fade optional but not required for v1.
- **[Risk] Over-styling action buttons** → **Mitigation**: reuse compact button patterns already used elsewhere (border + small padding); don’t invent a new button system.

## Migration Plan

Pure CSS (+ optional class attribute). Ship in one pass. Rollback: revert `style.css` (and the one-line `tasks.js` class if added).

## Open Questions

- None — card chrome and 8px gap are fixed by the approved plan.

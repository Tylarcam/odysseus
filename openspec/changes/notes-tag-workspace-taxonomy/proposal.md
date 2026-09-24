## Why

Notes tags are a single space-separated `label` string with no layers, no canonical casing, and no workspace model. The filter bar treats every token as equal, so entropy grows (`Approval` vs `approval`, project names mixed with intents, untagged notes dumped in Default). We need a low-entropy taxonomy and a one-time cleanup of live note data before new notes keep making it worse.

## What Changes

- Introduce a three-layer tag taxonomy: **scope** (exactly 1), **intent** (0–1), **topic** (0–3).
- Encode layers in the existing `Note.label` field (no new table). Workspaces are saved/derived filters over Layer 1 + Layer 2, not a separate entity.
- Audit every distinct tag, cluster synonyms, and produce a mapping before any write.
- Require explicit sign-off on the mapping, then migrate labels with a restoreable backup.
- Document the convention in `TAG_CONVENTIONS.md` and enforce max-3 topics + required scope on save going forward.
- Light UI: group the labels bar by layer; do not rebuild the notes app.

## Capabilities

### New Capabilities

- `notes-tag-taxonomy`: Three-layer tag model (scope / intent / topic), encoding in `label`, workspace-as-filter convention, save-time caps, and `TAG_CONVENTIONS.md`.
- `notes-tag-audit-cleanup`: Inventory, clustering, synonym merge, backup, sign-off-gated retag, singleton handling, and ≥30% unique-tag reduction.

### Modified Capabilities

- (none)

## Impact

- `core/database.py` — `Note.label` remains the store; no schema break unless a later decision adds prefix tokens only.
- `routes/note_routes.py` — optional validation on create/update (scope required, topic cap).
- `static/js/notes.js` — labels bar grouping; client-side cap on topic chips.
- New scripts under `scripts/` (audit + migrate + restore).
- `docs/TAG_CONVENTIONS.md` (or repo-root equivalent).
- Backup JSON of `notes.id` + `label` before writes.
- Tests for parse/encode, synonym merge, and migration dry-run.

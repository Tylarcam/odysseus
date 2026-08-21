# Notes tag conventions

Odysseus Notes has **one store** (`notes.label`, space-separated) and **no workspace field**. Lifecycle is a *view*, not a tag. Tags exist so you can find things later — they are not a filing cabinet.

Convention as of 2026-08-17 (cleanup A). Agents: `manage_notes` / `POST /api/codex/todos` with `label`.

---

## Views (not tags)

| View | How it is computed |
|------|-------------------|
| Inbox | No topic tags (untagged). Also the Default chip. |
| Today | `due_date` today/overdue, or a goal’s next unchecked step |
| Later | Has topic tags, not in Today |
| Archive | `archived = true` |
| Agent | `handoff_*` / `agent_session_id`, or reserved tag `handoff-cursor` / topic `agent` |

Do **not** stamp `daily`, `project`, `research`, or `personal` on every note. Untagged is a valid Inbox state.

---

## Reserved tags (do not count toward the topic cap)

| Tag | Meaning |
|-----|---------|
| `calendar` | Reminder notes created from the calendar. Leave them here so calendar polling still works. |
| `imported` | File import. |
| `handoff-cursor` | Note was handed to Cursor. Prefer Agent view over adding this by hand. |

`due_date` **is** the reminder. Do not also store a `reminder` tag.

---

## Topics (0–3 per note)

Lowercase kebab-case. Space-separated. Max **three** topic tags after reserved ones.

**Projects / bodies of work:** `hermes` · `mycelia` · `jobs` · `lili` · `cursor` · `npr` · `sporangium` · `search-as-code` · `heyclicky` · `playlab` · `fable5`

**Streams:** `revenue` · `blackboard` · `digest` · `research` · `draft` · `swarm-health` · `interview` · `forager` · `thank-you` · `security`

**Optional intent** (only when the note *is* that, not “about” it): `review` · `feedback` · `decision`

Reuse an existing topic before inventing a new one. If a name is used once and is not a real project, skip the tag.

---

## How to tag a new note

1. Capture first. Empty `label` is fine.
2. If it belongs to a named project, add that one topic.
3. Add at most two more topics if they help retrieval.
4. Set `due_date` for reminders. Use `calendar` only for calendar-origin notes.

### Merge rules (apply without asking)

- Case-insensitive: `Job` = `job` = `jobs` (writes are **lowercased** in the API and Notes panel)
- `Application` / `Tracker` → `jobs`
- `inbox_triage` → `inbox-triage`
- `Swarm` / `Approval` → `mycelia` / `review`
- `sac` / loom-sac slugs → `search-as-code`
- Commas are not separators the UI understands — use spaces (`lili gamma`, not `lili,gamma`)
- No dates-as-tags, no `closed-*` provenance stamps (archive the note instead)

---

## Backup

Last bulk rewrite: 2026-08-17. Pre-change dump: `.tmp/notes-tag-backup-20260817.json`.

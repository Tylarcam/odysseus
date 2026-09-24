## Context

Notes store tags in one nullable `Note.label` string (whitespace-separated tokens). The labels bar in `static/js/notes.js` treats every token as a peer filter, plus synthetic chips (All, Default, Reminders, Goals). There is no workspace table, no casing canonicalization, and no cap on how many tags a note can carry.

The operator’s live chip row already shows the entropy problem: `#Approval #Feedback #Information #LiLi #Literacy #Presentation #Swarm #agent #agents #blackboard #blockers` sitting next to Default/Reminders. “Workspaces” in the agent spec are a desired organizing lens, not an existing entity.

This change is a **data + convention** cleanup with the lightest possible save-path enforcement so entropy does not bounce back. It is not a notes-app rebuild.

## Goals / Non-Goals

**Goals:**

- Audit every distinct tag (counts, singletons, untagged notes).
- Adopt a 3-layer taxonomy and encode it in `label` without a schema migration.
- Treat workspaces as Layer 1 (+ optional Layer 2) filters, not a new table.
- Backup, require mapping sign-off, then retag.
- Cut unique tag count by ≥30% vs audit baseline.
- Publish `docs/TAG_CONVENTIONS.md` and enforce scope=1, topics≤3 on save.

**Non-Goals:**

- Rebuilding the notes UI beyond labels-bar grouping and save-time caps.
- Hard-deleting notes.
- Moving notes between a workspace table (none exists).
- Auto-retagging notes that still have >3 topics after mapping (flag for manual review).
- Changing archive/delete/reminder behavior.

## Decisions

1. **Keep `Note.label` as the only store.** Prefix reserved layers so they cannot collide with topics:
   - Scope: `scope:<daily|project|research|personal>` (exactly one)
   - Intent: `intent:<feedback|review|decision>` (zero or one)
   - Topic: unprefixed kebab-case tokens (zero to three)
   - Example: `scope:project intent:review hermes jobs`
   - Alternative considered: new JSON/columns. Rejected — out of scope for schema, breaks every agent that already writes `label`.

2. **Canonical storage is lowercase kebab-case.** Display maps a small proper-noun table (`hermes` → Hermes, `search-as-code` → search-as-code). Dedup without asking: case, singular/plural, known synonyms (`interview-prep` → `interview`, `sac` → `search-as-code`, `agents` → `agent` only if the audit shows they are the same cluster — otherwise keep distinct).

3. **Workspaces = filter chips for the four scopes.** Intent chips are optional secondary filters. A “project workspace” is `scope:project` plus a topic naming the project (`hermes`, `swarm`). Do not invent `workspace:` tokens.

4. **Two scripts, two phases.**
   - `scripts/notes_tag_audit.py` — read-only inventory + suggested mapping YAML.
   - `scripts/notes_tag_migrate.py` — writes only with `--apply` after `--map` is present; always writes `notes-label-backup-<timestamp>.json` first; `--restore` reverts from that file.
   - Notes with 4+ topics post-map are listed in a `needs-review` report and **skipped**.

5. **Untagged notes get `scope:daily` only.** No invented topics.

6. **Singletons merge or drop as topics, never as new reserved vocab.** If a singleton is clearly a proper project name used once, keep it as a topic (projects can be rare). If it is a typo/synonym, merge.

7. **Save-time enforcement is server-authoritative.** PUT/POST notes normalize and reject (or auto-trim with a warning) when scope is missing or topics > 3. Client mirrors the cap so the form cannot emit an illegal string. Existing illegal rows are not rewritten until migrate `--apply`.

8. **Labels bar groups chips:** Scope | Intent | Topics. Synthetic chips (All, Default, Reminders, Goals) stay first. Default means “no topic tags” still; after migration every note has a scope so Default should shrink to near-zero.

## Risks / Trade-offs

- [Risk] Prefix tokens are visible if a client prints raw `label` → Mitigation: `_visibleNoteTags` / chip renderer strip `scope:` / `intent:` and group them.
- [Risk] Agents writing free-form labels bypass the UI → Mitigation: API normalize on write; conventions doc for agents.
- [Risk] ≥30% unique-tag cut depends on live data → Mitigation: audit prints baseline; migrate aborts if projected unique count misses the target unless `--force-under-target`.
- [Risk] Wrong synonym merge (e.g. `agent` vs `agents`) → Mitigation: mapping YAML is the contract; no apply without sign-off.
- [Risk] Backup file contains titles/labels → Mitigation: write under `.tmp/` (gitignored) or `data/backups/`; never commit.

## Migration Plan

1. Dry-run audit → `openspec/changes/notes-tag-workspace-taxonomy/audit/` (or `.tmp/notes-tag-audit/`) with inventory + draft map.
2. Operator edits/approves the map.
3. `migrate --apply` writes backup then labels.
4. Rollback: `migrate --restore <backup.json>`.
5. Land `TAG_CONVENTIONS.md` and save-path validation in the same change so new notes follow the map.

## Open Questions

- Confirm reserved intent list stays at three (`feedback`, `review`, `decision`) after the audit (e.g. whether `approval` is intent:review or a topic).
- Whether API should **auto-default** missing scope to `daily` or **reject** the write. Default proposal: auto-default on agent writes, reject on explicit UI save if the user deleted the scope chip.
- Display casing for project topics (Hermes vs hermes) — small proper-noun map vs always kebab.

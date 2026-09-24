## 1. Shared label codec

- [ ] 1.1 Add parse/encode helpers for `scope:` / `intent:` / topic tokens (lowercase kebab, one scope, ≤3 topics)
- [ ] 1.2 Add tests for case merge, singular/plural, synonym map, prefix collision (`daily` topic vs `scope:daily`)

## 2. Audit (read-only)

- [ ] 2.1 Write `scripts/notes_tag_audit.py` — inventory, frequencies, singletons, untagged ids, draft mapping YAML
- [ ] 2.2 Run audit against live notes and record baseline unique-tag count in the change folder (do not write labels)

## 3. Mapping sign-off (human gate)

- [ ] 3.1 Cluster draft map into scope / intent / topic; merge Approval/approval, Jobs/Job, sac→search-as-code
- [ ] 3.2 Flag notes that would still have >3 topics after mapping (manual review list)
- [ ] 3.3 Get explicit operator sign-off on the mapping YAML before any `--apply`

## 4. Migration

- [ ] 4.1 Write `scripts/notes_tag_migrate.py` — dry-run by default; `--apply` writes `{id,label}` backup then UPDATEs
- [ ] 4.2 Default untagged notes to `scope:daily` only; skip over-cap notes
- [ ] 4.3 Abort `--apply` if projected unique tags miss ≥30% reduction unless override flag
- [ ] 4.4 Implement `--restore` from backup JSON; add tests for dry-run / apply / restore

## 5. Conventions + save-path enforcement

- [ ] 5.1 Write `docs/TAG_CONVENTIONS.md` (3 layers, reserved vocab, workspace = scope filter, agent label rules)
- [ ] 5.2 Normalize/validate `label` on note create/update in `routes/note_routes.py`
- [ ] 5.3 Group labels bar chips by Scope | Intent | Topics; strip prefixes in display
- [ ] 5.4 Cap topic chips at 3 in the note form; do not rebuild the rest of the notes UI

## 6. Verify

- [ ] 6.1 After approved `--apply`, confirm every migrated note has exactly one scope and ≤3 topics
- [ ] 6.2 Confirm unique tag count ≤ 70% of baseline; leftover needs-review list is empty or accepted
- [ ] 6.3 Run codec + migrate pytest modules

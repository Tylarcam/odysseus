# V.A.U.L.T. Command Center — Product Requirements (Completion PRD)

> **Status:** Phase 1–2 partial ship (2026-07-04). This document lists remaining work and defines done for the ultimate situation-room HUD.

---

## Agent completion prompt (copy-paste)

```
You are completing the V.A.U.L.T. (Odysseus Command Center) build in repo odysseus.
Read docs/vault-cmd-center-prd.md and docs/odysseus-data-dictionary.md §5–§8 first.

Context: Phase 1–2 landed — minimize (−), Esc dismiss, priority_queue, branch_health,
Three.js constellation (static/js/cmdCenterScene.js), job attention panel (cmdCenterJobs.js),
hero explain/cta, wire timestamps, suggested_commands. Backend: services/home/cmd_center.py.

Your job: finish Phases 3–4 per the PRD acceptance criteria below. Work in phases (≤5 files
per phase). Run pytest tests/test_home_dashboard.py after backend changes. Do not break
modalManager minimize/restore for cmd-center-overlay.

North star: open vault → within 5s user knows what's on fire, clicks once to act, leaves via − or Esc.

Priority order:
1. Job attention panel → full actions (open job, apply package, mark applied)
2. Wire /api/voice/stats into cmd-center payload + Audio I/O degraded state
3. Live updates while vault open (poll or SSE)
4. Morning ritual mode (first open of day)
5. Three.js polish (tooltips, WebGL fallback, reduced-motion)
6. Docs + tests (API route test, JS smoke test, update data dictionary)

Match existing HUD aesthetic (#a6e22e / #7fff00, JetBrains Mono, injected #cmd-center-styles).
Lazy-load three from static/lib/three.module.js only when vault opens.
```

---

## Vision

**V.A.U.L.T.** is a full-viewport **situation room** — not a duplicate sidebar. It answers: *What needs me right now, and what's one click away?*

| Gesture | Behavior |
|---------|----------|
| `−` (top bar) | Minimize → dock chip; preserve HUD + scene state |
| Esc | Dismiss vault (full teardown) |
| Rail / sidebar CMD Center | Closed → open · Minimized → restore · Open → minimize |
| Click priority row / hero / 3D node / pill | Open tool on top; vault stays open |

---

## What shipped (Phase 1–2 partial)

| Area | Done |
|------|------|
| Chrome | `−` minimize, Esc dismiss, no ✕, sync label under clock |
| Backend | `priority_queue`, `branch_health`, `hero.explain/cta_label/branch`, `suggested_commands`, `jobs_detail`, `synced_at`, `plan_note_id` |
| Hero logic | Relay → Agency jobs → Directives → Notes priority |
| Left rail | Priority Queue (sorted), honest vitals (no fake sparklines), documents w/ relative time |
| Center | Three.js orbital branch map, float cards, hero overlay w/ explain + CTA |
| Right rail | Suggested commands, command deck, Audio I/O hint updated, AI Wire w/ ts + branch |
| Actions | `plan_today`, `jobs` → job panel, `open_session` keeps vault, relay copy cmd |
| Lifecycle | `restoreFn` resumes clock/scene; sidebar minimizes when open |
| Tests | `test_build_cmd_center_maps_live_odysseus_surfaces` updated |
| Assets | `static/lib/three.module.js` vendored |

**Key files**

| File | Role |
|------|------|
| `services/home/cmd_center.py` | Payload aggregator |
| `routes/home_routes.py` | `GET /api/home/cmd-center` |
| `static/js/cmdCenter.js` | HUD shell + render + actions |
| `static/js/cmdCenterScene.js` | Three.js branch constellation |
| `static/js/cmdCenterJobs.js` | Job attention read-only modal |

---

## Gap inventory — not done

### P0 — Trust & needle-moving (must ship)

| ID | Gap | Current state | Target |
|----|-----|---------------|--------|
| G-01 | ~~Job panel is read-only~~ **Done 2026-07-04** | Rows have Open / Apply package / Mark applied buttons, wired to `/api/jobs/*` | `static/js/cmdCenterJobs.js` — click row's Open shows job detail (status, scores, apply_url); Apply package fetches `/api/jobs/<id>/apply-package`; Mark applied posts `/api/jobs/<id>/mark-applied` and disables the button |
| G-02 | **No dedicated Job Pipeline HUD surface** | Only modal list | Full `jobPipeline` panel (or embed job routes UI) opened from Agency hero/CTA |
| G-03 | **AM Report / Morning card** | `jobs` action opens generic panel | Open morning brief **note** when no jobs; else job panel; card subtitle deterministic |
| G-04 | **Plan Today when no plan note** | Falls back to Notes list | Create plan note from template or open wizard |
| G-05 | **Voice stats not in API** | `voice.state` hardcoded `standby` in builder | `home_routes` passes `/api/voice/stats` SLO into `build_cmd_center(voice=...)`; Audio I/O shows Degraded |
| G-06 | **Comms branch is fake** | Always "Inbox ready" | Unread / needs-triage count from email poller or inbox API |
| G-07 | **Mem branch opens Notes** | `action: notes` | Open Brain / memory modal (`tool-memory-btn`) |
| G-08 | **Core branch** | Refresh only | Diagnostics link (settings health) or honest "all systems" from scheduler/MCP ping |
| G-09 | **Auto-sync on restore** | Manual Vault Sync only | If `synced_at` > 60s on restore, background `_fetchData()` |
| G-10 | **API route test** | Unit test on builder only | `test_home_routes` GET `/api/home/cmd-center` with auth fixture |

### P1 — Live situation room

| ID | Gap | Target |
|----|-----|--------|
| G-11 | **No live updates while open** | Poll every 30s or SSE `GET /api/home/cmd-center/stream` for relay/job changes; update scene + wire without full repaint flash |
| G-12 | **3D node hover** | Tooltip w/ branch summary (same as pill title) |
| G-13 | **Intel + Voice missing from pill row** | Add to `status` filter or collapsible "more branches" |
| G-14 | **Wire filters** | Chips: All · Relay · Agency · Prod · Chat |
| G-15 | **Vitals real deltas** | `+N today` / `updated today: N` from `updated_at` windows (no fake history DB required) |
| G-16 | **Priority queue from handoff only in test** | E2E test with jobs-only hero path |

### P2 — Morning ritual & power UX

| ID | Gap | Target |
|----|-----|--------|
| G-17 | **Morning ritual mode** | First open per calendar day: highlight Morning card, hero = jobs+handoffs, suggested = AM Report · Plan · Inbox; optional "Start day →" runs sync + plan note |
| G-18 | **Directive actions** | Snooze / mark done from queue row (notes API) |
| G-19 | **Relay Watcher UX** | Modal explaining relay + copy install cmd (not toast-only) |
| G-20 | **Voice panel expand** | Click Audio I/O → mini drawer: gateway state, last error, link to voice settings |
| G-21 | **Hero expandable** | Chevron to show full priority rationale / top 3 queue items |
| G-22 | **Recent commands** | localStorage last 3 command-deck actions at top |
| G-23 | **Keyboard shortcut** | Dedicated vault toggle (e.g. document in shortcuts modal); fix global toggle-window to minimize vault |

### P3 — Three.js & visual polish

| ID | Gap | Target |
|----|-----|--------|
| G-24 | **WebGL fallback** | Static SVG constellation if WebGL fails; toast once |
| G-25 | **Reduced motion** | `prefers-reduced-motion`: static map, no particles |
| G-26 | **Bloom / postprocessing** | Optional EffectComposer pass (phase 3.5; perf gate) |
| G-27 | **3D node labels** | Sprite or HTML overlay labels on hover |
| G-28 | **Camera focus** | Ease camera toward clicked branch |
| G-29 | **Styles consolidation** | Optional move `#cmd-center-styles` to `style.css` theming vars |
| G-30 | **Mobile** | Touch orbit; hide 3D on narrow view optional; test dock chip |
| G-36 | **Display settings** | Gear in vault top bar toggles each HUD panel on/off; prefs in `localStorage`; ⓘ popovers explain goal/provenance/action |

### Display settings (shipped)

**Done when:**

- [x] Gear button in vault top bar opens in-vault Display drawer
- [x] Each toggleable panel maps to `data-cmd-vis` id (see component atlas)
- [x] Preferences persist in `localStorage` (`odysseus-cmd-center-visibility`)
- [x] Reset defaults restores all panels visible
- [x] Panel headers show ⓘ with goal / provenance / action from atlas
- [x] Mobile tab shows empty hint when all panels in that tab are hidden
- [x] Full atlas doc: `docs/vault-cmd-center-component-atlas.md`

---

| ID | Gap | Target |
|----|-----|--------|
| G-31 | **Data dictionary stale** | Update §5 with new payload keys (`priority_queue`, `branch_health`, `jobs_detail`, etc.) |
| G-32 | **System map alignment** | Regenerate `odysseus-system-map.excalidraw` w/ V.A.U.L.T. 2.0 nodes |
| G-33 | **Frontend tests** | `tests/test_cmd_center_js.py` or playwright smoke: open vault, minimize, Esc |
| G-34 | **Docker verify** | Confirm `static/lib/three.module.js` served in container; add to Dockerfile COPY if needed |
| G-35 | **Error UX** | Stale-while-revalidate: show last good data + amber sync badge vs red banner |

---

## Phase plan & acceptance criteria

### Phase 3 — Live ops + real branches (P0 + P1)

**Files (expected):** `cmd_center.py`, `home_routes.py`, `cmdCenter.js`, `cmdCenterScene.js`, `cmdCenterJobs.js`

**Done when:**

- [x] Job panel rows open job detail / apply package
- [ ] Voice SLO reflected in `branch_health.voice` and Audio I/O
- [ ] Comms shows real unread or "0 unread"
- [ ] Mem → Brain; Core → diagnostics
- [ ] Vault auto-refreshes on restore if stale > 60s
- [ ] Poll or SSE updates wire + 3D pulse without closing vault
- [ ] 3D hover tooltips work
- [ ] `pytest tests/test_home_dashboard.py` + new route test pass

### Phase 4 — Ritual + polish (P2 + P3 + P4)

**Done when:**

- [ ] Morning ritual mode works (localStorage day key)
- [ ] Relay watcher modal
- [ ] WebGL fallback + reduced motion
- [ ] Wire filters
- [ ] Data dictionary §5 updated
- [ ] At least one frontend smoke test

---

## API contract (target — extend §5)

### `GET /api/home/cmd-center`

Existing keys plus ensure documented:

```yaml
synced_at: ISO8601
branch_health: [{ id, label, state, count, summary, action }]
priority_queue: [{ id, kind, title, subtitle, branch, urgency, action, target_id, ts }]
hero: { label, title, value, unit, velocity, explain, cta_label, branch, action, target_id }
suggested_commands: [{ id, label, action, target_id? }]
jobs_detail: { ready_to_apply[], needs_review[], headline }
plan_note_id: string | null
audio: { tts, label, hint, slo?: { p95_mic_to_first_audio_ms, degraded: bool } }
counts: { ..., handoffs_in_progress }
```

### New (Phase 3)

```yaml
GET /api/home/cmd-center/stream   # SSE optional
  events: relay_changed | jobs_changed | sync_tick
  payload: partial branch_health + wire + hero deltas
```

---

## Section dictionary (for edits)

| Section ID | Label | Done? | Remaining |
|------------|-------|-------|-----------|
| `topbar.brand` | V.A.U.L.T. | ✓ | Acronym tooltip |
| `topbar.status` | Branch pills | partial | Intel/Voice, real Comms/Core |
| `topbar.clock` | Clock | ✓ | — |
| `topbar.sync` | Sync label | ✓ | Auto-retry on restore |
| `topbar.minimize` | − | ✓ | — |
| `rail.left.vitals` | System Vitals | ✓ | Real deltas (+today) |
| `rail.left.directives` | Priority Queue | ✓ | Snooze/done |
| `rail.left.documents` | Documents | ✓ | Collapse when crowded |
| `stage.sphere` | Three.js map | partial | Tooltips, fallback, labels |
| `stage.cards` | Intent dock | partial | Deterministic AM/plan |
| `stage.hero` | Primary directive | ✓ | Expandable detail |
| `rail.right.suggested` | Suggested | ✓ | Ritual-aware |
| `rail.right.commands` | Command deck | partial | Recent commands |
| `rail.right.audio` | Audio I/O | partial | Live SLO, expand panel |
| `rail.right.wire` | AI Wire | partial | Filters, live push |
| `shell.jobs_panel` | Job attention | ✓ | — |

---

## Out of scope (explicit)

- COMMUNITY / SALES / FINANCE branches (see data dictionary §7 gaps)
- Creator metrics (YT subs, etc.)
- Publishing pipeline / carousels
- Replacing Agent Bin or full email client inside vault

---

## Success metrics

1. **Time-to-action:** User opens vault → clicks hero or #1 queue item in < 10s (manual test script)
2. **Truth:** No button label mismatch (every command deck label matches action)
3. **Calm → hot:** Relay busy visibly pulses in pills + 3D within 1 sync cycle
4. **Jobs path:** Jobs ready → panel → apply package without opening unrelated tools
5. **Leave:** `−` and Esc work with voice active (voice stop scoped to chat, not vault)

---

## Reference

- Design discussion: Cursor session V.A.U.L.T. UX (2026-07-04)
- System map: `docs/odysseus-system-map.excalidraw`
- Data dictionary: `docs/odysseus-data-dictionary.md`
- Tests: `tests/test_home_dashboard.py`

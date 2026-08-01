# Handoff: PROD Left Rail Task UI

> **Odysseus landing (2026-07-30):** Orbital ProdLeft + TaskCard chrome is integrated into
> V.A.U.L.T. CMD Center `PROD` → left rail `task_board` in `static/js/cmdCenter.js`.
> Data comes from live `priority_queue` / `directives` (prod branch), not vault-orbital localStorage seed.
> See status mapping + API gaps in the session return notes.

**Source repo:** `C:\Users\tylar\.minimax-agent\projects\vault-orbital`  
**Surface:** Topbar `PROD` → left rail (`width: 300`) → `ProdLeft` + `TaskCard`  
**Verdict:** Style + behavior confirmed in code this session. Screenshot matches seed tasks (`t1`, `t2`, `t6`).

---

## Direct path map

```
App shell
  vault-orbital/src/App.tsx                    ← left rail slot: left:0, top:56, bottom:56, width:300
  vault-orbital/src/index.css                  ← font, page bg #050608, scrollbar
  vault-orbital/src/components/Topbar.tsx      ← PROD tab switch (setActiveTab)

Left rail entry
  vault-orbital/src/components/LeftPanel.tsx
    L5–17   LeftPanel shell (padding/gap)
    L11     tab === 'PROD' → <ProdLeft />
    L242–297 ProdLeft (TASKS header, buckets, add input)
    L300–337 TaskCard (card chrome, status, due, action)

Shared chrome
  vault-orbital/src/components/Panel.tsx
    L3–18   Panel
    L21–28  PanelHeader ("TASKS")
    L31–41  Section ("OPEN" / "BLOCKED" / "DONE")
    L61–76  Tag (priority badge)

Data + colors + actions
  vault-orbital/src/data.ts                    ← Task type, seed tasks
  vault-orbital/src/store.ts
    L163–164 priorityColor
    L165–166 statusColor
    L86–99   addTask
    L106–108 moveTask
  vault-orbital/src/components/BriefModal.tsx  ← openModal('task', id) detail
```

---

## Layout / spacing (exact)

| Layer | Path | Values |
|--------|------|--------|
| Left rail frame | `App.tsx` ~L44 | `width: 300`, `top: 56`, `bottom: 56` |
| Rail inner | `LeftPanel.tsx` L8 | `padding: 12px 14px`, `gap: 10`, `flex column`, `overflowY: auto` |
| TASKS panel | `Panel.tsx` L6–12 | `padding: 10px 12px`, border `#1a2030`, top border `#2a3040`, blur 6px, gradient bg |
| Section header | `Panel.tsx` L34 | `gap: 6`, `marginBottom: 4`, `marginTop: 4` |
| **Between task cards** | `Panel.tsx` L39 | **`gap: 6`** (column flex) |
| Task card padding | `LeftPanel.tsx` L309 | **`padding: 8px 10px`** |
| Card row gaps | `LeftPanel.tsx` L314, L321 | header `gap: 6`; footer `gap: 4`, `marginTop: 6` |
| Description offset | `LeftPanel.tsx` L319 | `marginTop: 4`, `lineHeight: 1.4` |

---

## Left color tab

**Not status — priority.**

```308:308:vault-orbital/src/components/LeftPanel.tsx
        borderLeft: `3px solid ${priorityColor(task.priority)}`,
```

```163:164:vault-orbital/src/store.ts
export const priorityColor = (p: string) =>
  p === 'critical' ? '#ff4a4a' : p === 'high' ? '#ff9a3c' : p === 'medium' ? '#ffd966' : '#4dd8e6'
```

- Width: **3px** via `borderLeft`
- Card fill: `rgba(10,14,20,0.55)`
- Full border: `1px solid #1a2030`
- Seed high tasks (`t1`/`t2`) → orange tab `#ff9a3c` (matches screenshot)

---

## Status labels (QUEUED / IN PROGRESS / BLOCKED)

```316:316:vault-orbital/src/components/LeftPanel.tsx
        <span style={{ fontSize: 8, color: statusColor(task.status), letterSpacing: '0.1em' }}>{task.status.toUpperCase().replace('_', ' ')}</span>
```

```165:166:vault-orbital/src/store.ts
export const statusColor = (s: string) =>
  s === 'done' ? '#4dd8e6' : s === 'in_progress' ? '#ff9a3c' : s === 'blocked' ? '#ff4a4a' : '#7a8694'
```

| Status | Display | Color |
|--------|---------|-------|
| `in_progress` | `IN PROGRESS` | `#ff9a3c` |
| `queued` | `QUEUED` | `#7a8694` (dim) |
| `blocked` | `BLOCKED` | `#ff4a4a` |
| `done` | `DONE` | `#4dd8e6` |

Title: `11px`, `#c8d0d8`, `fontWeight: 500`  
Description: `10px`, `#7a8694`

---

## Due date

```323:323:vault-orbital/src/components/LeftPanel.tsx
        <span style={{ fontSize: 9, color: '#5a6470' }}>due {new Date(task.due).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
```

Format: `due Aug 1` (en-US short month + day). Field: `Task.due` ISO in `data.ts`.

New tasks default due = now + 7 days (`store.ts` `addTask`).

---

## Priority tag + action button

**Tag** (`Panel.tsx` Tag): `8px`, uppercase, `padding: 1px 5px`, `letterSpacing: 0.15em`, bg `rgba(77,216,230,0.08)`, border `#2a3040`, color `#7a8694` → shows `HIGH` / `MEDIUM` / etc.

**Action** (`LeftPanel.tsx` L325–334):

| Current | Button |
|---------|--------|
| `queued` | `→ START` → `in_progress` |
| `in_progress` | `→ DONE` → `done` |
| else (`blocked` / `done`) | `→ REOPEN` → `queued` |

Button chrome: transparent bg, `1px solid #1f2630`, color `#7a8694`, `9px`, `padding: 2px 6px`.

---

## OPEN / BLOCKED / DONE buckets

```247:295:vault-orbital/src/components/LeftPanel.tsx
  const open = tasks.filter((t) => t.status === 'queued' || t.status === 'in_progress')
  const blocked = tasks.filter((t) => t.status === 'blocked')
  const done = tasks.filter((t) => t.status === 'done')
  // ...
  <Section label="OPEN" count={open.length}>...</Section>
  <Section label="BLOCKED" count={blocked.length}>...</Section>
  <Section label="DONE" count={done.length}>
    {done.slice(0, 4).map(...)}  // capped at 4
  </Section>
```

**Section divider** (`Panel.tsx` L31–41):

- Label: `9px`, `#5a6470`, `letterSpacing: 0.25em`
- Count: `9px`, `#ff9a3c` (the orange “1” in `BLOCKED 1`)
- Rule: `height: 1`, `#1a2030`, flex grow

Summary chips above lists (`ProdLeft` L277–280): OPEN `#ff9a3c`, BLOCKED `#ff4a4a`, DONE `#4dd8e6`, `9px`.

---

## Task data shape + seed (screenshot)

```9:19:vault-orbital/src/data.ts
export type Task = {
  id: string
  title: string
  description: string
  priority: Priority
  status: TaskStatus
  due: string  // ISO date
  tags: string[]
  directive: 'prod' | 'intel' | 'comms' | 'chat'
  createdAt: string
}
```

| id | Title | Status | Priority | Due offset |
|----|-------|--------|----------|------------|
| `t1` | RSVP Brett Gaylor PhD defence | `in_progress` | high | +2d |
| `t2` | Alkira cover letter — second pass | `queued` | high | +1d |
| `t6` | Cover letter framework v3 — doc | `blocked` | medium | +4d |

Persistence: `localStorage` key `vault_orbital_state_v1` (`data.ts` L199).

---

## Global tokens

| Token | Value | Where |
|-------|-------|-------|
| Font | JetBrains Mono / Courier New | `index.css`, `App.tsx` |
| Page bg | `#050608` | `index.css`, `App.tsx` |
| Body text | `#c8d0d8` | global |
| Accent orange | `#ff9a3c` | tabs, headers, in_progress, high |
| Danger | `#ff4a4a` | blocked / critical |
| Cyan | `#4dd8e6` | done / low |
| Muted | `#5a6470` / `#7a8694` | meta / queued |

---

## Runtime flow

```
[Topbar PROD] Topbar.tsx
      │ setActiveTab('PROD')
      ▼
[LeftPanel] LeftPanel.tsx L11
      │
      ▼
[ProdLeft] filter open/blocked/done
      │
      ├─ Panel + PanelHeader "TASKS"
      ├─ Section OPEN  → TaskCard[]
      ├─ Section BLOCKED → TaskCard[]   ← screenshot "BLOCKED 1"
      └─ Section DONE (max 4)
            │
            ├─ click card → openModal('task', id) → BriefModal.tsx
            └─ action btn → moveTask(id, next) → store.ts
```

**UNCHANGED for style-only work:** `Scene.tsx`, Rings/Core/HUD, RightPanel, Audiobar, telemetry tick.

---

## Paste-ready builder prompt

```
CONTEXT: vault-orbital PROD left-rail Tasks. Spec is validated. Do not re-litigate tokens/spacing.

GOAL: [state your change — e.g. restyle TaskCard / extract CSS / match Section count styling]

HARD CONSTRAINTS:
- Touch only files listed in the phase.
- Keep left accent as priorityColor (3px borderLeft), NOT status.
- Keep statusColor mapping: queued=#7a8694, in_progress=#ff9a3c, blocked=#ff4a4a, done=#4dd8e6.
- Keep Section gap between cards at 6; card padding 8px 10px.
- Keep due format: `due {month short} {day}` en-US.
- Keep moveTask cycle: queued→in_progress→done; else→queued (button labels START/DONE/REOPEN).
- Do not change seed data unless asked.

PHASE 1 — Inspect (no edits)
- Read LeftPanel.tsx ProdLeft + TaskCard (L242–337)
- Read Panel.tsx Section + Tag
- Read store.ts priorityColor/statusColor/moveTask
- Verify: grep "borderLeft" LeftPanel.tsx shows priorityColor on TaskCard

PHASE 2 — Implement [your change] in:
- vault-orbital/src/components/LeftPanel.tsx
- [optional] vault-orbital/src/components/Panel.tsx
Stop for approval.

PHASE 3 — Verify
- npm run build (or tsc -b)
- Manual: switch to PROD; confirm OPEN cards, BLOCKED section count orange, QUEUED dim, due string, START/DONE buttons
- Diff touches ONLY listed files

ACCEPTANCE:
- [ ] Card gap still 6px via Section children stack
- [ ] High priority left tab #ff9a3c / 3px
- [ ] QUEUED uses #7a8694; BLOCKED #ff4a4a
- [ ] Action labels match status table above
```
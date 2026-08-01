## Context

V.A.U.L.T. already ranks work in `priority_queue` / hero and opens surfaces via `_runAction` (notes, jobs, agent_bin). Handoff packets already exist (`createHandoffDocument` in `static/js/handoff.js`). Mobile sheets already use vertical swipe-to-dismiss (`panelSheet.js`). This change adds a horizontal triage layer on top of that stack without replacing rails.

## Goals / Non-Goals

**Goals:**
- One modal for triage of needs-attention / overdue items
- Mobile: swipe left = delegate (Relay handoff), swipe right = finished
- Desktop: same actions via buttons
- Server-owned `attention_stack` so hero count and stack cannot drift

**Non-Goals:**
- Replacing Priority Queue / AI Wire panels
- New WebSocket triage channel
- Multi-card drag physics beyond one-at-a-time advance
- Changing globe base rendering beyond refresh after actions

## Decisions

1. **Stack source = new `attention_stack` on cmd-center payload**  
   Filter/rank from the same inputs as priority queue (handoffs needing attention, jobs review/ready, overdue notes). Client does not re-sort. Hero OVERDUE value SHOULD equal overdue-note count when that path is active; stack length is the triage queue size (may include handoffs/jobs).

2. **Entry = hero click / CTA when stack non-empty**  
   Intercept `cmd-hero` / CTA instead of immediate `_runAction`. Empty stack keeps prior standby behavior (toast / sync).

3. **Delegate = `createHandoffDocument`**  
   Default target `cursor`; card shows target chips (cursor / claude / hermes / odysseus). Existing handoff cards: open Agent Bin focused on that item — do not duplicate packets.

4. **Finished = kind-specific**  
   - note: archive (or clear due_date if archive unavailable) via notes API  
   - job: mark-applied / dismiss review via jobs API  
   - handoff: resolve via agent-bin / handoff status API  
   Optimistic remove + refetch.

5. **New module `cmdCenterDirective.js`**  
   Keeps swipe/DOM out of the already-large `cmdCenter.js`; parent only opens/closes and refreshes data.

6. **Swipe axis**  
   Horizontal on the card surface; cancel if vertical intent dominates (mirror panelSheet’s axis-cancel pattern, inverted). Threshold ~80px or velocity.

## Risks / Trade-offs

- **[Risk] Wrong finish API for a kind leaves item stuck** → Mitigation: toast on failure; do not advance card until success (or rollback optimistic remove).
- **[Risk] Duplicate handoffs if user swipes twice** → Mitigation: disable gestures while request in flight; advance only after success.
- **[Risk] Hero still bound to `_runAction` elsewhere** → Mitigation: only intercept hero/CTA entry; queue rows keep existing open behavior.
- **[Trade-off] Default target cursor** may not match preference → chips on card; persist last target in `localStorage`.

## Migration Plan

1. Ship OpenSpec artifacts then code behind existing vault open.
2. Restart Odysseus container so Python `attention_stack` is live (bind mount alone does not reload imports).
3. Hard-refresh client for new JS module.
4. Rollback: restore hero `_runAction` path; ignore unused `attention_stack` field.

## Open Questions

- None blocking — defaults above match operator decisions (handoff on left; Tinder stack).

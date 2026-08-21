/**
 * V.A.U.L.T. Directive Triage — swipeable needs-attention stack.
 * Swipe left / Delegate → Relay handoff. Swipe right / Done → mark finished.
 * Double-tap (mobile) / double-click → peek the next card without acting.
 */

import { createHandoffDocument, notifyHandoffPickup } from './handoff.js';
import agentBinModule from './agentBin.js';
import { openJobAttentionPanel } from './cmdCenterJobs.js';

const API_BASE = typeof window !== 'undefined' ? window.location.origin : '';
const TARGET_KEY = 'odysseus-cmd-handoff-target';
const VALID_TARGETS = ['cursor', 'claude', 'hermes', 'odysseus'];
const SWIPE_PX = 80;
const SWIPE_V = 0.35;
const DOUBLE_TAP_MS = 500;
const DOUBLE_TAP_PX = 40;
const REAL_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let _root = null;
let _stack = [];
let _index = 0;
let _busy = false;
let _onRefresh = null;
let _onOpenItem = null;
let _target = 'cursor';
let _escBound = null;
let _suppressClickUntil = 0;

function _esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _readTarget() {
  try {
    const t = localStorage.getItem(TARGET_KEY);
    if (t && VALID_TARGETS.includes(t)) return t;
  } catch { /* ignore */ }
  return 'cursor';
}

function _writeTarget(t) {
  _target = VALID_TARGETS.includes(t) ? t : 'cursor';
  try { localStorage.setItem(TARGET_KEY, _target); } catch { /* ignore */ }
}

function _chipClass(status) {
  if (status === 'overdue') return 'red';
  if (status === 'due') return 'amber';
  return 'ok';
}

function _ensureStyles() {
  if (document.getElementById('cmd-directive-styles')) return;
  const style = document.createElement('style');
  style.id = 'cmd-directive-styles';
  style.textContent = `
.cmd-triage-backdrop {
  position: absolute; inset: 0; z-index: 40;
  background: rgba(5,6,8,.78); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.cmd-triage-modal {
  width: min(440px, 96vw); max-height: min(78vh, 640px);
  background: #0a0e14; border: 1px solid #2a3040;
  box-shadow: 0 0 48px rgba(0,0,0,.45); display: flex; flex-direction: column;
  font-family: "JetBrains Mono", ui-monospace, monospace; color: #c8d0d8;
}
.cmd-triage-h {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 12px 14px; border-bottom: 1px solid #1a2030;
  font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; color: #5a6470;
}
.cmd-triage-h strong { color: #ff9a3c; letter-spacing: 0.08em; }
.cmd-triage-close {
  background: none; border: 1px solid #1f2630; color: #7a8694;
  font: 600 10px/1 inherit; padding: 6px 8px; cursor: pointer; letter-spacing: 0.12em;
}
.cmd-triage-close:hover { color: #c8d0d8; border-color: #2a3040; }
.cmd-triage-stage {
  position: relative; flex: 1; min-height: 220px; overflow: hidden; padding: 18px 16px 12px;
  touch-action: pan-y;
}
.cmd-triage-card {
  position: relative; border: 1px solid #1a2030; background: rgba(10,14,20,0.95);
  border-left: 3px solid #4dd8e6;
  padding: 16px 14px 14px; min-height: 180px; will-change: transform;
  transition: box-shadow .15s; -webkit-user-select: none; user-select: none;
}
.cmd-triage-card.peek-in { animation: cmd-triage-peek .22s ease; }
@keyframes cmd-triage-peek {
  from { opacity: .4; transform: translateY(14px); }
  to { opacity: 1; transform: none; }
}
.cmd-triage-peek {
  display: none; margin-top: 12px; font-size: 8px; letter-spacing: 0.16em;
  text-transform: uppercase; opacity: 0.38;
}
.cmd-triage-card.dragging { transition: none; }
.cmd-triage-card[data-intent="left"] { box-shadow: -10px 0 28px rgba(255,154,60,.25); border-color: #ff9a3c; }
.cmd-triage-card[data-intent="right"] { box-shadow: 10px 0 28px rgba(77,216,230,.22); border-color: #4dd8e6; }
.cmd-triage-hint {
  position: absolute; top: 50%; transform: translateY(-50%);
  font-size: 9px; letter-spacing: 0.2em; opacity: 0; pointer-events: none; transition: opacity .12s;
}
.cmd-triage-hint.left { left: 10px; color: #ff9a3c; }
.cmd-triage-hint.right { right: 10px; color: #4dd8e6; }
.cmd-triage-card[data-intent="left"] .cmd-triage-hint.left,
.cmd-triage-card[data-intent="right"] .cmd-triage-hint.right { opacity: 0.9; }
.cmd-triage-kind {
  font-size: 8px; letter-spacing: 0.18em; opacity: 0.55; margin-bottom: 8px; text-transform: uppercase;
}
.cmd-triage-title { font-size: 14px; color: #c8d0d8; font-weight: 500; line-height: 1.4; margin-bottom: 10px; }
.cmd-triage-meta { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; margin-bottom: 10px; }
.cmd-triage-chip {
  font-size: 7px; letter-spacing: 0.1em; padding: 2px 6px; border: 1px solid; text-transform: uppercase;
}
.cmd-triage-chip.red { color: #ff5c49; border-color: #7a2a22; background: rgba(255,92,73,.08); }
.cmd-triage-chip.amber { color: #ffb347; border-color: #7a5a22; background: rgba(255,179,71,.08); }
.cmd-triage-chip.ok { color: #4dd8e6; border-color: #2a3040; }
.cmd-triage-preview { font-size: 10px; color: #7a8694; line-height: 1.45; }
.cmd-triage-targets { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; }
.cmd-triage-targets button {
  background: none; border: 1px solid #1f2630; color: #7a8694;
  font: 600 8px/1 inherit; letter-spacing: 0.12em; padding: 5px 8px; cursor: pointer; text-transform: uppercase;
}
.cmd-triage-targets button[aria-pressed="true"] { color: #4dd8e6; border-color: #2a3040; }
.cmd-triage-actions {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; padding: 12px 14px 14px;
  border-top: 1px solid #1a2030;
}
.cmd-triage-actions button {
  background: none; border: 1px solid #1f2630; color: #c8d0d8;
  font: 600 9px/1 inherit; letter-spacing: 0.14em; padding: 11px 6px; cursor: pointer; text-transform: uppercase;
}
.cmd-triage-actions button:hover { color: #4dd8e6; border-color: #2a3040; }
.cmd-triage-actions button:disabled { opacity: 0.35; cursor: default; }
.cmd-triage-actions .done { border-color: rgba(77,216,230,.45); color: #4dd8e6; }
.cmd-triage-actions .delegate { border-color: rgba(255,154,60,.45); color: #ff9a3c; }
.cmd-triage-empty { padding: 40px 20px; text-align: center; color: #5a6470; font-size: 11px; }
@media (max-width: 720px) {
  .cmd-triage-backdrop { align-items: flex-end; padding: 0; }
  .cmd-triage-modal { width: 100%; max-height: 85vh; border-radius: 10px 10px 0 0; }
  .cmd-triage-peek { display: block; }
}
`;
  document.head.appendChild(style);
}

/** Next card index when peeking the deck (wraps; no-op on empty). */
export function nextPeekIndex(index, length) {
  const n = Math.max(0, Number(length) || 0);
  if (n <= 0) return 0;
  const i = Number(index);
  const cur = Number.isFinite(i) ? i : 0;
  return ((cur % n) + n + 1) % n;
}

function _current() {
  return _stack[_index] || null;
}

function _renderCard(item) {
  if (!item) {
    return `<div class="cmd-triage-empty">Clear deck — nothing left to triage</div>`;
  }
  const chip = item.due_label
    ? `<span class="cmd-triage-chip ${_chipClass(item.status)}">${_esc(item.due_label)}</span>`
    : '';
  const branch = item.branch ? `<span class="cmd-triage-chip ok">${_esc(String(item.branch).toUpperCase())}</span>` : '';
  const targets = VALID_TARGETS.map((t) =>
    `<button type="button" data-triage-target="${t}" aria-pressed="${t === _target ? 'true' : 'false'}">${_esc(t)}</button>`
  ).join('');
  return `
    <div class="cmd-triage-hint left">← DELEGATE</div>
    <div class="cmd-triage-hint right">DONE →</div>
    <div class="cmd-triage-card" id="cmd-triage-card" style="border-left-color:${_priorityAccent(item)}">
      <div class="cmd-triage-kind">${_esc(item.kind || 'item')} · ${_index + 1}/${_stack.length}</div>
      <div class="cmd-triage-title">${_esc(item.title || 'Untitled')}</div>
      <div class="cmd-triage-meta">${chip}${branch}</div>
      <div class="cmd-triage-preview">${_esc(item.preview || item.subtitle || '')}</div>
      ${_stack.length > 1 ? '<div class="cmd-triage-peek">double tap to peek next</div>' : ''}
      ${item.kind === 'handoff' ? '' : `<div class="cmd-triage-targets">${targets}</div>`}
    </div>`;
}

function _paintCard(opts = {}) {
  const stage = _root?.querySelector('.cmd-triage-stage');
  if (!stage) return;
  stage.innerHTML = _renderCard(_current());
  const card = stage.querySelector('#cmd-triage-card');
  _wireCardSwipe(card);
  if (opts.peek && card) card.classList.add('peek-in');
  const item = _current();
  const delBtn = _root.querySelector('[data-triage-act="delegate"]');
  const doneBtn = _root.querySelector('[data-triage-act="done"]');
  const openBtn = _root.querySelector('[data-triage-act="open"]');
  if (delBtn) {
    delBtn.disabled = _busy || !item;
    delBtn.textContent = item?.kind === 'handoff' ? 'OPEN BIN' : 'DELEGATE';
  }
  if (doneBtn) doneBtn.disabled = _busy || !item;
  if (openBtn) openBtn.disabled = _busy || !item;
  const count = _root.querySelector('.cmd-triage-count');
  if (count) count.textContent = String(_stack.length);
}

async function _advance() {
  _stack.splice(_index, 1);
  if (_index >= _stack.length) _index = Math.max(0, _stack.length - 1);
  if (!_stack.length) {
    closeDirectiveTriage();
    try { await _onRefresh?.(); } catch { /* ignore */ }
    return;
  }
  _paintCard();
  try { await _onRefresh?.(); } catch { /* ignore */ }
}

function _cyclePeek() {
  if (_busy || !_stack.length) return;
  _suppressClickUntil = Date.now() + 500;
  if (_stack.length > 1) _index = nextPeekIndex(_index, _stack.length);
  _paintCard({ peek: true });
}

function _itemId(item) {
  return String(item?.target_id || item?.id || '').trim();
}

function _isPersistedId(id) {
  return REAL_ID_RE.test(String(id || '').trim());
}

/** Orbital seed ids (t1/t2/t6) and other demo keys — never treat as live notes. */
function _isSeedOrFakeId(id) {
  const s = String(id || '').trim();
  if (!s) return true;
  return /^(t[0-9]+|demo[-_].+|seed[-_].+)$/i.test(s);
}

function _priorityAccent(item) {
  const st = String(item?.status || '').toLowerCase();
  if (st === 'overdue') return '#ff4a4a';
  if (st === 'due') return '#ff9a3c';
  return '#4dd8e6';
}

async function _readError(res) {
  try {
    const body = await res.json();
    return body?.detail || body?.error || body?.message || `${res.status}`;
  } catch {
    return `${res.status}`;
  }
}

async function _patchNote(id, patch) {
  const res = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(await _readError(res));
  return res;
}

function _resolveOpenAction(item) {
  if (item?.action) return item.action;
  if (item?.kind === 'job') return 'jobs';
  if (item?.kind === 'handoff') return 'agent_bin';
  if (item?.kind === 'task') return 'open_task';
  return 'open_note';
}

async function _delegate() {
  const item = _current();
  if (!item || _busy) return;
  _busy = true;
  _paintCard();
  try {
    if (item.kind === 'handoff') {
      agentBinModule?.openAgentBin?.();
      window.uiModule?.showToast?.('Opened Agent Bin', 2500);
      await _advance();
      return;
    }
    const result = await createHandoffDocument({
      apiBase: API_BASE,
      target: _target,
      title: item.title || 'Directive',
      goal: item.title || 'Triage item',
      context: [
        `Kind: ${item.kind || 'item'}`,
        item.due_label ? `Due: ${item.due_label}` : '',
        item.branch ? `Branch: ${item.branch}` : '',
        item.id ? `Source id: ${item.id}` : '',
      ].filter(Boolean),
      noteBody: item.preview || item.subtitle || '',
      next: ['Pick up in Agent Bin / Relay and close the loop.'],
      source: 'odysseus',
    });
    await notifyHandoffPickup({
      target: result.target || _target,
      docId: result.docId,
      noteId: result.noteId,
      relayStatus: result.relayStatus,
    });
    await _advance();
  } catch (err) {
    console.warn('triage delegate failed', err);
    window.uiModule?.showToast?.(`Delegate failed: ${err.message || err}`, 3500);
  } finally {
    _busy = false;
    if (_root) _paintCard();
  }
}

async function _finish() {
  const item = _current();
  if (!item || _busy) return;
  _busy = true;
  _paintCard();
  const id = _itemId(item);
  try {
    if (!id || _isSeedOrFakeId(id)) {
      throw new Error('Missing live server id');
    }
    if (item.kind === 'note' || item.kind === 'handoff') {
      if (!_isPersistedId(id)) throw new Error('Note has no server id');
      // due_date:null is ignored (only non-null writes). Empty string clears due.
      await _patchNote(id, { archived: true, pinned: false, due_date: '' });
    } else if (item.kind === 'job') {
      const res = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(id)}/mark-applied`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!res.ok && res.status !== 409) throw new Error(await _readError(res));
    } else {
      throw new Error(`Unsupported kind ${item.kind}`);
    }
    window.uiModule?.showToast?.('Marked done', 2200);
    await _advance();
  } catch (err) {
    console.warn('triage finish failed', err);
    window.uiModule?.showToast?.(`Done failed: ${err.message || err}`, 3500);
  } finally {
    _busy = false;
    if (_root) _paintCard();
  }
}

async function _openItem() {
  const item = _current();
  if (!item || _busy) return;
  const id = _itemId(item);
  const action = _resolveOpenAction(item);
  // Close triage so the destination surface isn't buried under the modal.
  closeDirectiveTriage();
  try {
    if (_onOpenItem) {
      await _onOpenItem(action, id);
      return;
    }
    if (action === 'open_note' || item.kind === 'note') {
      if (id && window.notesModule?.openNote) await window.notesModule.openNote(id);
      else window.notesModule?.openNotes?.();
      return;
    }
    if (action === 'agent_bin' || item.kind === 'handoff') {
      agentBinModule?.openAgentBin?.();
      return;
    }
    if (action === 'jobs' || item.kind === 'job') {
      openJobAttentionPanel({});
      return;
    }
    if (action === 'open_task' || item.kind === 'task') {
      window.tasksModule?.openTasks?.(id || undefined);
      return;
    }
    window.uiModule?.showToast?.(`No opener for ${action || item.kind || 'item'}`, 2500);
  } catch (err) {
    console.warn('triage open failed', err);
    window.uiModule?.showToast?.(`Open failed: ${err.message || err}`, 3500);
  }
}

function _wireCardSwipe(card) {
  if (!card) return;
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastT = 0;
  let velocity = 0;
  let dragging = false;
  let cancelled = false;
  let lastTapT = 0;
  let lastTapX = 0;
  let lastTapY = 0;

  const reset = () => {
    card.classList.remove('dragging');
    card.dataset.intent = '';
    card.style.transform = '';
    card.style.transition = 'transform 0.18s ease';
  };

  card.addEventListener('touchstart', (e) => {
    if (_busy || e.touches.length !== 1) return;
    if (e.target.closest('button')) return;
    const t = e.touches[0];
    startX = t.clientX;
    startY = t.clientY;
    lastX = startX;
    lastT = e.timeStamp;
    velocity = 0;
    dragging = false;
    cancelled = false;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (cancelled || _busy) return;
    const t = e.touches[0];
    const dx = t.clientX - startX;
    const dy = Math.abs(t.clientY - startY);
    if (!dragging) {
      if (dy > 28 && dy > Math.abs(dx) * 1.2) {
        cancelled = true;
        reset();
        return;
      }
      if (Math.abs(dx) > 10) {
        dragging = true;
        card.classList.add('dragging');
      } else {
        return;
      }
    }
    const dt = e.timeStamp - lastT;
    if (dt > 0) velocity = velocity * 0.6 + ((t.clientX - lastX) / dt) * 0.4;
    lastX = t.clientX;
    lastT = e.timeStamp;
    e.preventDefault();
    card.style.transform = `translateX(${dx}px) rotate(${dx * 0.03}deg)`;
    card.dataset.intent = dx < -40 ? 'left' : dx > 40 ? 'right' : '';
  }, { passive: false });

  const end = (e) => {
    const t = e?.changedTouches?.[0];
    const endX = t ? t.clientX : lastX;
    const endY = t ? t.clientY : startY;

    if (dragging) {
      dragging = false;
      lastTapT = 0;
      const dx = lastX - startX;
      const goLeft = dx < -SWIPE_PX || (dx < -24 && velocity < -SWIPE_V);
      const goRight = dx > SWIPE_PX || (dx > 24 && velocity > SWIPE_V);
      if (goLeft) {
        card.style.transition = 'transform 0.2s ease';
        card.style.transform = 'translateX(-120%) rotate(-8deg)';
        setTimeout(() => { reset(); _delegate(); }, 160);
        return;
      }
      if (goRight) {
        card.style.transition = 'transform 0.2s ease';
        card.style.transform = 'translateX(120%) rotate(8deg)';
        setTimeout(() => { reset(); _finish(); }, 160);
        return;
      }
      reset();
      return;
    }

    if (cancelled || _busy) {
      lastTapT = 0;
      return;
    }
    if (e?.target?.closest?.('button')) {
      lastTapT = 0;
      return;
    }

    const now = Date.now();
    if (lastTapT && (now - lastTapT) < DOUBLE_TAP_MS
        && Math.hypot(endX - lastTapX, endY - lastTapY) < DOUBLE_TAP_PX) {
      lastTapT = 0;
      _cyclePeek();
      return;
    }
    lastTapT = now;
    lastTapX = endX;
    lastTapY = endY;
  };

  card.addEventListener('touchend', end, { passive: true });
  card.addEventListener('touchcancel', () => {
    dragging = false;
    lastTapT = 0;
    reset();
  }, { passive: true });
  card.addEventListener('dblclick', (e) => {
    if (_busy || e.target.closest('button')) return;
    if (Date.now() < _suppressClickUntil) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    _cyclePeek();
  });
}

function _onRootClick(e) {
  if (Date.now() < _suppressClickUntil) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  const close = e.target.closest('[data-triage-act="close"]');
  if (close) {
    e.preventDefault();
    closeDirectiveTriage();
    return;
  }
  const targetBtn = e.target.closest('[data-triage-target]');
  if (targetBtn) {
    e.preventDefault();
    _writeTarget(targetBtn.dataset.triageTarget);
    _paintCard();
    window.uiModule?.showToast?.(`Handoff target → ${_target}`, 1800);
    return;
  }
  const act = e.target.closest('[data-triage-act]');
  if (!act) return;
  e.preventDefault();
  const which = act.dataset.triageAct;
  if (which === 'delegate') void _delegate();
  else if (which === 'done') void _finish();
  else if (which === 'open') void _openItem();
}

/**
 * @param {{
 *   stack?: object[],
 *   mount?: HTMLElement,
 *   onRefresh?: () => Promise<void>|void,
 *   onOpenItem?: (action: string, id: string) => void,
 * }} opts
 */
export function openDirectiveTriage({
  stack = [],
  mount,
  onRefresh,
  onOpenItem,
} = {}) {
  const host = mount || document.getElementById('cmd-center-root') || document.body;
  if (!host) return false;
  const list = Array.isArray(stack)
    ? stack.filter((x) => x && !_isSeedOrFakeId(_itemId(x)))
    : [];
  if (!list.length) {
    window.uiModule?.showToast?.('Nothing to triage', 2200);
    return false;
  }

  closeDirectiveTriage();
  _ensureStyles();
  _stack = list.slice();
  _index = 0;
  _busy = false;
  _onRefresh = typeof onRefresh === 'function' ? onRefresh : null;
  _onOpenItem = typeof onOpenItem === 'function' ? onOpenItem : null;
  _target = _readTarget();

  const el = document.createElement('div');
  el.className = 'cmd-triage-backdrop';
  el.id = 'cmd-triage-backdrop';
  el.innerHTML = `
    <div class="cmd-triage-modal" role="dialog" aria-label="Directive triage">
      <div class="cmd-triage-h">
        <span>TRIAGE — <strong class="cmd-triage-count">${_stack.length}</strong> OPEN</span>
        <button type="button" class="cmd-triage-close" data-triage-act="close" aria-label="Close">ESC</button>
      </div>
      <div class="cmd-triage-stage"></div>
      <div class="cmd-triage-actions">
        <button type="button" class="delegate" data-triage-act="delegate">DELEGATE</button>
        <button type="button" data-triage-act="open">OPEN</button>
        <button type="button" class="done" data-triage-act="done">DONE</button>
      </div>
    </div>`;
  host.appendChild(el);
  _root = el;
  el.addEventListener('click', (e) => {
    if (Date.now() < _suppressClickUntil) {
      e.preventDefault();
      return;
    }
    if (e.target === el) closeDirectiveTriage();
    else _onRootClick(e);
  });
  _escBound = (ev) => {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      closeDirectiveTriage();
    }
  };
  document.addEventListener('keydown', _escBound, true);
  _paintCard();
  return true;
}

export function closeDirectiveTriage() {
  if (_escBound) {
    document.removeEventListener('keydown', _escBound, true);
    _escBound = null;
  }
  _root?.remove();
  _root = null;
  _stack = [];
  _index = 0;
  _busy = false;
  _suppressClickUntil = 0;
}

export function isDirectiveTriageOpen() {
  return !!_root;
}

export default {
  openDirectiveTriage,
  closeDirectiveTriage,
  isDirectiveTriageOpen,
  nextPeekIndex,
};

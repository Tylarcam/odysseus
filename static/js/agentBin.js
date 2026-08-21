/**
 * Agent Bin — aggregated handoff inbox from note-backed handoffs.
 */

import uiModule from './ui.js';
import { makeWindowDraggable } from './windowDrag.js';
import * as Modals from './modalManager.js';
import {
  handoffStatusLabel,
  handoffTargetIsExternal,
  handoffChipTitle,
  handoffClipboardText,
  handoffPickupHint,
  resolveHandoffDocId,
  openHandoffDocument,
  openHandoffAgentSession,
} from './handoff.js';

const API_BASE = window.location.origin;

let _open = false;
let _activeTab = 'attention';
let _data = {
  needs_attention: [],
  in_progress: [],
  done: [],
  counts: { needs_attention: 0, in_progress: 0, done: 0, total: 0 },
};
let _pollInterval = null;
let _badgeInterval = null;
let _escHandler = null;
let _loading = false;
let _error = '';

function _esc(text) {
  if (uiModule?.esc) return uiModule.esc(text);
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _noteTitle(note) {
  const t = String(note?.title || '').trim();
  if (t) return t;
  const c = String(note?.content || '').trim();
  if (c) return c.split('\n')[0].slice(0, 80);
  return 'Untitled handoff';
}

function _formatWhen(note) {
  const raw = note?.handoff_at || note?.updated_at;
  if (!raw) return '';
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function _defaultTab() {
  const c = _data.counts || {};
  if ((c.needs_attention || 0) > 0) return 'attention';
  if ((c.in_progress || 0) > 0) return 'progress';
  return _activeTab || 'attention';
}

async function _fetchHandoffs() {
  _loading = true;
  _error = '';
  try {
    const res = await fetch(`${API_BASE}/api/notes/handoffs`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`Handoffs fetch failed (${res.status})`);
    const payload = await res.json();
    if (!payload || typeof payload !== 'object' || !payload.counts) {
      throw new Error('Unexpected handoffs payload');
    }
    _data = payload;
  } catch (err) {
    _error = err?.message || String(err);
    console.warn('Agent Bin fetch failed', err);
  } finally {
    _loading = false;
  }
}

function _tabItems() {
  if (_activeTab === 'progress') return _data.in_progress || [];
  if (_activeTab === 'done') return _data.done || [];
  return _data.needs_attention || [];
}

function _renderRow(note) {
  const target = note.handoff_target || '';
  const status = note.handoff_relay_status || '';
  const label = handoffStatusLabel(target, status);
  const statusCls = status ? ` note-handoff-tag--${status}` : '';
  const title = _noteTitle(note);
  const when = _formatWhen(note);
  const outcome = note.handoff_outcome
    ? `<div class="agent-bin-outcome">${_esc(String(note.handoff_outcome).slice(0, 200))}${note.handoff_outcome.length > 200 ? '…' : ''}</div>`
    : '';
  const external = handoffTargetIsExternal(target);
  const sessionId = note.handoff_relay_session_id || note.agent_session_id;
  const agentBtn = (!external)
    ? `<button type="button" class="memory-toolbar-btn agent-bin-open-agent" data-session-id="${_esc(sessionId)}" data-note-id="${_esc(note.id)}">Open agent</button>`
    : '';
  const cliChip = (external && sessionId)
    ? `<span class="agent-bin-cli" title="${_esc(sessionId)}">CLI ${_esc(String(sessionId).slice(0, 8))}</span>`
    : '';
  const looksBroken = status === 'failed'
    || (note.handoff_outcome && /node\.exe|integrityerror|unique constraint/i.test(note.handoff_outcome));
  const retryBtn = (looksBroken && _activeTab !== 'done')
    ? `<button type="button" class="memory-toolbar-btn agent-bin-retry" data-note-id="${_esc(note.id)}">Retry relay</button>`
    : '';
  const markDoneBtn = (!note.archived && _activeTab !== 'done')
    ? `<button type="button" class="memory-toolbar-btn agent-bin-mark-done" data-note-id="${_esc(note.id)}">Mark done</button>`
    : '';
  const copyBtn = (external && status === 'queued')
    ? `<button type="button" class="memory-toolbar-btn agent-bin-copy-hint" data-target="${_esc(target)}" data-doc-id="${_esc(note.handoff_doc_id)}">Copy pickup</button>`
    : '';

  return `
    <div class="agent-bin-row" data-note-id="${_esc(note.id)}" title="${_esc(handoffChipTitle(target, status))}">
      <div class="agent-bin-row-head">
        <span class="note-handoff-tag agent-bin-status${statusCls}">${_esc(label)}</span>
        <span class="agent-bin-target">${target ? `→ ${_esc(target)}` : ''}</span>
        ${cliChip}
        ${when ? `<span class="agent-bin-when">${_esc(when)}</span>` : ''}
      </div>
      <div class="agent-bin-title">${_esc(title)}</div>
      ${outcome}
      <div class="agent-bin-actions">
        <button type="button" class="memory-toolbar-btn agent-bin-open-doc" data-doc-id="${_esc(note.handoff_doc_id)}">Open doc</button>
        <button type="button" class="memory-toolbar-btn agent-bin-open-note" data-note-id="${_esc(note.id)}">Open note</button>
        ${agentBtn}
        ${retryBtn}
        ${copyBtn}
        ${markDoneBtn}
      </div>
    </div>`;
}

function _syncTabCounts() {
  const modal = document.getElementById('agent-bin-modal');
  if (!modal) return;
  const c = _data.counts || {};
  const set = (sel, n) => {
    const el = modal.querySelector(sel);
    if (el) el.textContent = String(n ?? 0);
  };
  set('#agent-bin-count-attention', c.needs_attention);
  set('#agent-bin-count-progress', c.in_progress);
  set('#agent-bin-count-done', c.done);
}

function _renderList() {
  const body = document.querySelector('#agent-bin-modal .agent-bin-body');
  if (!body) return;
  _syncTabCounts();
  const items = _tabItems();
  if (_loading && !items.length) {
    body.innerHTML = '<div class="agent-bin-empty">Loading handoffs…</div>';
    return;
  }
  if (_error && !items.length) {
    body.innerHTML = `<div class="agent-bin-empty">Could not load handoffs (${_esc(_error)}).</div>`;
    return;
  }
  if (!items.length) {
    const msg = _activeTab === 'attention'
      ? 'Nothing needs your attention.'
      : _activeTab === 'progress'
        ? 'No handoffs in progress.'
        : 'No completed handoffs yet.';
    body.innerHTML = `<div class="agent-bin-empty">${msg}</div>`;
    return;
  }
  body.innerHTML = items.map(_renderRow).join('');
}

function _switchTab(tab) {
  _activeTab = tab;
  const modal = document.getElementById('agent-bin-modal');
  if (!modal) return;
  modal.querySelectorAll('.agent-bin-tab').forEach(btn => {
    const on = btn.dataset.tab === tab;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  _renderList();
}

function _wireRowActions(modal) {
  modal.addEventListener('click', async (e) => {
    const docBtn = e.target.closest('.agent-bin-open-doc');
    if (docBtn) {
      const docId = docBtn.dataset.docId;
      if (docId) await openHandoffDocument(docId);
      return;
    }
    const noteBtn = e.target.closest('.agent-bin-open-note');
    if (noteBtn) {
      const noteId = noteBtn.dataset.noteId;
      if (noteId) {
        const notes = window.notesModule;
        if (notes?.openNote) await notes.openNote(noteId);
        else notes?.openPanel?.();
      }
      return;
    }
    const agentBtn = e.target.closest('.agent-bin-open-agent');
    if (agentBtn) {
      const sid = agentBtn.dataset.sessionId;
      const row = agentBtn.closest('.agent-bin-row');
      const noteId = row?.dataset?.noteId;
      const docBtn = row?.querySelector('.agent-bin-open-doc');
      const docId = docBtn?.dataset?.docId;
      await openHandoffAgentSession({ sessionId: sid, noteId, docId });
      return;
    }
    const copyBtn = e.target.closest('.agent-bin-copy-hint');
    if (copyBtn) {
      const docId = resolveHandoffDocId({ id: copyBtn.dataset.docId });
      const clip = handoffClipboardText(copyBtn.dataset.target, docId);
      const hint = handoffPickupHint(copyBtn.dataset.target, docId);
      try {
        await navigator.clipboard.writeText(clip || hint);
        uiModule.showToast?.(clip ? `Copied — paste in chat: ${clip}` : 'Pickup hint copied', {
          duration: 12000,
          leadingIcon: 'check',
        });
      } catch {
        uiModule.showToast?.(hint, { duration: 18000 });
      }
      return;
    }
    const retryBtn = e.target.closest('.agent-bin-retry');
    if (retryBtn) {
      const noteId = retryBtn.dataset.noteId;
      if (!noteId) return;
      retryBtn.disabled = true;
      try {
        const res = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(noteId)}/handoff/retry`, {
          method: 'POST',
          credentials: 'same-origin',
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Retry failed (${res.status})`);
        }
        const data = await res.json();
        uiModule.showToast?.(
          data.target === 'odysseus'
            ? 'Relay re-queued — Odysseus agent will run shortly'
            : 'Relay re-queued — start handoff-relay-watcher.ps1 -RunAgent',
          { duration: 8000 },
        );
        await _fetchHandoffs();
        _activeTab = 'progress';
        _switchTab('progress');
        refreshBadge();
      } catch (err) {
        uiModule.showError?.('Could not retry relay: ' + (err.message || err));
        retryBtn.disabled = false;
      }
      return;
    }
    const doneBtn = e.target.closest('.agent-bin-mark-done');
    if (doneBtn) {
      const noteId = doneBtn.dataset.noteId;
      if (!noteId) return;
      try {
        const res = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(noteId)}`, {
          method: 'PUT',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ archived: true }),
        });
        if (!res.ok) throw new Error('Archive failed');
        uiModule.showToast?.('Marked done');
        await _fetchHandoffs();
        _renderList();
        refreshBadge();
        window.notesModule?.refreshDueBadge?.({ force: true });
      } catch (err) {
        uiModule.showError?.('Could not mark done: ' + (err.message || err));
      }
    }
  });
}

function _startPolling() {
  _stopPolling();
  _pollInterval = setInterval(async () => {
    if (!_open) return;
    await _fetchHandoffs();
    _renderList();
    refreshBadge();
  }, 15000);
}

function _stopPolling() {
  if (_pollInterval) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
}

export function openAgentBin() {
  if (Modals.isMinimized('agent-bin-modal')) {
    Modals.restore('agent-bin-modal');
    _open = true;
    _fetchHandoffs().then(() => {
      _activeTab = _defaultTab();
      _switchTab(_activeTab);
      refreshBadge();
    });
    _startPolling();
    return;
  }
  if (_open) return;

  _open = true;
  _activeTab = 'attention';
  _loading = true;
  _error = '';

  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'agent-bin-modal';
  modal.innerHTML = `
    <div class="modal-content agent-bin-content">
      <div class="modal-header">
        <h4><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>Agent Bin</h4>
        <span style="flex:1"></span>
        <button class="close-btn" id="agent-bin-close" aria-label="Close">✖</button>
      </div>
      <div class="memory-tabs agent-bin-tabs" role="tablist">
        <button class="memory-tab agent-bin-tab active" data-tab="attention" role="tab" aria-selected="true">
          Needs attention <span id="agent-bin-count-attention" class="memory-count">0</span>
        </button>
        <button class="memory-tab agent-bin-tab" data-tab="progress" role="tab" aria-selected="false">
          In progress <span id="agent-bin-count-progress" class="memory-count">0</span>
        </button>
        <button class="memory-tab agent-bin-tab" data-tab="done" role="tab" aria-selected="false">
          Done <span id="agent-bin-count-done" class="memory-count">0</span>
        </button>
      </div>
      <div class="modal-body agent-bin-body"></div>
    </div>
  `;
  document.body.appendChild(modal);

  const content = modal.querySelector('.modal-content');
  const header = modal.querySelector('.modal-header');
  if (content && header) makeWindowDraggable(modal, { content, header });

  modal.querySelectorAll('.agent-bin-tab').forEach(btn => {
    btn.addEventListener('click', () => _switchTab(btn.dataset.tab));
  });
  document.getElementById('agent-bin-close')?.addEventListener('click', closeAgentBin);
  modal.addEventListener('click', (e) => {
    if (uiModule.isTouchInsideModal?.()) return;
    if (e.target === modal) closeAgentBin();
  });
  _wireRowActions(modal);

  _escHandler = (e) => {
    if (e.key === 'Escape') closeAgentBin();
  };
  document.addEventListener('keydown', _escHandler);

  _renderList();
  _fetchHandoffs().then(() => {
    _activeTab = _defaultTab();
    _switchTab(_activeTab);
    refreshBadge();
  });
  _startPolling();

  Modals.register('agent-bin-modal', {
    railBtnId: 'rail-agent-bin',
    sidebarBtnId: 'tool-agent-bin-btn',
    closeFn: () => _doCloseAgentBin(),
    restoreFn: () => {},
  });
}

function _doCloseAgentBin() {
  if (!_open) return;
  _open = false;
  _stopPolling();
  if (_escHandler) {
    document.removeEventListener('keydown', _escHandler);
    _escHandler = null;
  }
  const modal = document.getElementById('agent-bin-modal');
  if (modal) {
    const content = modal.querySelector('.modal-content');
    if (content) {
      content.classList.add('modal-closing');
      content.addEventListener('animationend', () => modal.remove(), { once: true });
      setTimeout(() => { if (modal.parentElement) modal.remove(); }, 250);
    } else {
      modal.remove();
    }
  }
}

export function closeAgentBin() {
  if (!_open && !Modals.isMinimized('agent-bin-modal')) return;
  if (Modals.isRegistered('agent-bin-modal')) {
    Modals.close('agent-bin-modal');
  } else {
    _doCloseAgentBin();
  }
}

export function isAgentBinOpen() {
  if (Modals.isMinimized('agent-bin-modal')) return false;
  return _open;
}

function _updateBadge(count) {
  const railBtn = document.getElementById('rail-agent-bin');
  if (railBtn) {
    let badge = railBtn.querySelector('.rail-agent-bin-badge');
    if (count > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'rail-agent-bin-badge';
        railBtn.appendChild(badge);
      }
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.style.display = '';
    } else if (badge) {
      badge.remove();
    }
  }
  const sidebarBtn = document.getElementById('tool-agent-bin-btn');
  if (sidebarBtn) {
    const dot = sidebarBtn.querySelector('.tool-agent-bin-dot');
    if (dot) {
      dot.style.display = count > 0 ? '' : 'none';
    }
  }
}

export async function refreshBadge() {
  try {
    const res = await fetch(`${API_BASE}/api/notes/handoffs`, { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    _updateBadge((data?.counts?.needs_attention || 0) + (data?.counts?.in_progress || 0));
  } catch {
    /* non-fatal */
  }
}

export function startBadgePolling() {
  if (_badgeInterval) return;
  refreshBadge();
  _badgeInterval = setInterval(refreshBadge, 60 * 1000);
}

const agentBinModule = {
  openAgentBin,
  closeAgentBin,
  isAgentBinOpen,
  refreshBadge,
  startBadgePolling,
};

export default agentBinModule;
window.agentBinModule = agentBinModule;

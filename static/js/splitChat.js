/**
 * Split Chat — secondary chat pane (max 1) dockable/tileable in the workspace.
 * Primary chat stays in #chat-container; this opens a second session beside it.
 */

import uiModule from './ui.js';
import sessionModule from './sessions.js';
import chatRenderer from './chatRenderer.js';
import markdownModule from './markdown.js';
import Storage from './storage.js';
import { makeWindowDraggable } from './windowDrag.js';
import { applyEdgeDock } from './modalSnap.js';
import * as Modals from './modalManager.js';

const API_BASE = window.location.origin;

let _open = false;
let _sessionId = null;
let _streaming = false;
let _abort = null;
let _modal = null;

function _esc(s) {
  return uiModule.esc(String(s ?? ''));
}

export function isActive() {
  return _open;
}

export function getSecondarySessionId() {
  return _sessionId;
}

export function isStreaming() {
  return _streaming;
}

/** History element for the focused pane — used by chat.js when routing is needed. */
export function getActiveHistoryEl() {
  if (_open) return document.getElementById('split-chat-history');
  return document.getElementById('chat-history');
}

export function getActiveSessionId() {
  if (_open && _sessionId) return _sessionId;
  return sessionModule.getCurrentSessionId?.() || null;
}

function _primarySessionId() {
  return sessionModule.getCurrentSessionId?.() || null;
}

function _ensureModal() {
  if (_modal) return _modal;
  _modal = document.createElement('div');
  _modal.id = 'split-chat-modal';
  _modal.className = 'modal hidden';
  _modal.innerHTML = `
    <div class="modal-content split-chat-modal-content" role="dialog" aria-label="Split chat">
      <div class="modal-header split-chat-header">
        <h4 class="split-chat-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px;opacity:0.75"><rect x="2" y="3" width="8" height="18" rx="1"/><rect x="14" y="3" width="8" height="18" rx="1"/></svg>
          <span id="split-chat-title-text">Split chat</span>
        </h4>
        <span style="flex:1"></span>
        <button type="button" class="split-chat-focus-btn" id="split-chat-focus-btn" title="Switch main chat to this session">Focus</button>
        <button type="button" class="modal-minimize-btn" id="split-chat-minimize-btn" title="Minimize" aria-label="Minimize split chat">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round"><line x1="6" y1="18" x2="18" y2="18"/></svg>
        </button>
        <button type="button" class="close-btn split-chat-close-btn" id="split-chat-close-btn" aria-label="Close split chat">✖</button>
      </div>
      <div class="modal-body split-chat-body">
        <div id="split-chat-history" class="chat-history split-chat-history" role="log" aria-live="polite"></div>
        <div class="split-chat-input-bar">
          <textarea id="split-chat-message" rows="1" placeholder="Message in split chat…" autocomplete="off" aria-label="Split chat message"></textarea>
          <button type="button" class="send-btn split-chat-send-btn" id="split-chat-send-btn" title="Send">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
          </button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(_modal);

  const content = _modal.querySelector('.modal-content');
  const header = _modal.querySelector('.modal-header');
  makeWindowDraggable(_modal, {
    content,
    header,
    fsClass: 'split-chat-fullscreen',
    skipSelector: 'button, textarea, input, select, label',
    enableDock: true,
    enableLeftDock: true,
    onEnterFullscreen: () => content.classList.add('split-chat-fullscreen'),
    onExitFullscreen: () => {
      content.classList.remove('split-chat-fullscreen');
      if (window.innerWidth > 768) applyEdgeDock(_modal, 'right');
    },
  });

  _modal.querySelector('#split-chat-close-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    closeSplit();
  });
  _modal.querySelector('#split-chat-minimize-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    _registerModal();
    try { Modals.minimize('split-chat-modal'); } catch {}
  });
  _modal.querySelector('#split-chat-focus-btn')?.addEventListener('click', async (e) => {
    e.preventDefault();
    if (!_sessionId) return;
    await sessionModule.selectSession(_sessionId);
    closeSplit();
  });

  const form = _modal.querySelector('.split-chat-input-bar');
  form?.addEventListener('submit', (e) => { e.preventDefault(); _handleSubmit(); });
  _modal.querySelector('#split-chat-send-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    _handleSubmit();
  });
  const ta = _modal.querySelector('#split-chat-message');
  ta?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _handleSubmit();
    }
  });

  return _modal;
}

function _registerModal() {
  if (Modals.isRegistered?.('split-chat-modal')) return;
  Modals.register('split-chat-modal', {
    restoreFn: () => { openSplit(_sessionId, { skipLoad: true }); },
    closeFn: () => { closeSplit(); },
  });
}

function _setTitle(name) {
  const el = document.getElementById('split-chat-title-text');
  if (el) el.textContent = name || 'Split chat';
}

async function _loadHistory(sessionId) {
  const box = document.getElementById('split-chat-history');
  if (!box) return;
  box.innerHTML = '';
  box.classList.add('no-animate');

  const meta = sessionModule.getSessions?.().find(s => s.id === sessionId);
  _setTitle(meta?.name || 'Split chat');

  if (!sessionId) return;
  try {
    const res = await fetch(`${API_BASE}/api/history/${sessionId}`);
    const data = await res.json();
    const msgHistory = data.history || [];
    const modelName = data.model || meta?.model || null;
    if (!msgHistory.length) {
      box.innerHTML = '<div class="split-chat-empty">No messages yet — start typing below.</div>';
      return;
    }
    for (const msg of msgHistory) {
      const mmeta = msg.metadata ? { ...msg.metadata, _fromHistory: true } : null;
      let displayContent;
      if (typeof msg.content === 'string') displayContent = msg.content;
      else if (Array.isArray(msg.content)) {
        displayContent = msg.content.filter(p => p.type === 'text').map(p => p.text).join('\n').trim();
      } else displayContent = '';
      if (msg.role === 'user') {
        const t = displayContent.trim();
        if (t === 'Continue where you left off' || t.startsWith('Your message was cut off.')
            || t.startsWith('Your previous response was interrupted.')) continue;
      }
      chatRenderer.addMessage(msg.role, markdownModule.renderContent(displayContent), modelName, mmeta, box);
    }
    box.scrollTop = box.scrollHeight;
  } catch (err) {
    box.innerHTML = `<div class="split-chat-empty">Failed to load chat: ${_esc(err.message)}</div>`;
  } finally {
    box.classList.remove('no-animate');
  }
}

function _scrollSplitHistory() {
  const box = document.getElementById('split-chat-history');
  if (box) box.scrollTop = box.scrollHeight;
}

async function _handleSubmit() {
  if (_streaming || !_sessionId) return;
  const input = document.getElementById('split-chat-message');
  const btn = document.getElementById('split-chat-send-btn');
  const msg = (input?.value || '').trim();
  if (!msg) return;

  const box = document.getElementById('split-chat-history');
  if (!box) return;
  const empty = box.querySelector('.split-chat-empty');
  if (empty) empty.remove();

  const meta = sessionModule.getSessions?.().find(s => s.id === _sessionId);
  chatRenderer.addMessage('user', markdownModule.renderContent(msg), null, null, box);
  _scrollSplitHistory();
  if (input) input.value = '';

  _streaming = true;
  if (btn) btn.disabled = true;

  const holder = document.createElement('div');
  holder.className = 'msg msg-ai';
  const roleLabel = chatRenderer.shortModel?.(meta?.model) || 'AI';
  holder.innerHTML = `<div class="role">${_esc(roleLabel)}</div><div class="body"><div class="stream-content"></div></div>`;
  box.appendChild(holder);
  const contentEl = holder.querySelector('.stream-content');
  _scrollSplitHistory();

  const fd = new FormData();
  fd.append('session_id', _sessionId);
  fd.append('message', msg);
  fd.append('mode', (Storage.loadToggleState?.().mode || 'chat') === 'agent' ? 'agent' : 'chat');

  _abort = new AbortController();
  let accumulated = '';

  try {
    const res = await fetch(`${API_BASE}/api/chat_stream`, {
      method: 'POST',
      body: fd,
      signal: _abort.signal,
      headers: {
        'X-Tz-Offset': String(-new Date().getTimezoneOffset()),
        'X-Tz-Name': (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { return ''; } })(),
      },
    });
    if (!res.ok || !res.body) {
      const errText = `Error ${res.status}`;
      if (contentEl) contentEl.textContent = errText;
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') continue;
        try {
          const d = JSON.parse(raw);
          if (d.delta) {
            accumulated += d.delta;
            if (contentEl) {
              contentEl.innerHTML = markdownModule.processWithThinking(
                markdownModule.squashOutsideCode(accumulated)
              );
            }
            _scrollSplitHistory();
          }
        } catch (_) {}
      }
    }
    holder.dataset.raw = accumulated;
    if (window.hljs) {
      holder.querySelectorAll('pre code').forEach(b => window.hljs.highlightElement(b));
    }
  } catch (err) {
    if (err.name !== 'AbortError' && contentEl) {
      contentEl.textContent = err.message || 'Stream failed';
    }
  } finally {
    _streaming = false;
    _abort = null;
    if (btn) btn.disabled = false;
    if (input) input.focus();
  }
}

export async function openSplit(sessionId, { skipLoad = false, draftMessage = '' } = {}) {
  if (window.innerWidth <= 768) {
    uiModule.showToast?.('Split chat is desktop-only for now');
    return false;
  }
  if (window.compareModule?.isActive?.()) {
    uiModule.showToast?.('Close Compare before opening split chat');
    return false;
  }
  if (!sessionId) {
    uiModule.showToast?.('No session to open');
    return false;
  }
  if (sessionId === _primarySessionId()) {
    uiModule.showToast?.('Pick a different chat for the split pane');
    return false;
  }

  _sessionId = sessionId;
  const modal = _ensureModal();
  _registerModal();
  modal.classList.remove('hidden');
  document.body.classList.add('split-chat-active');
  _open = true;

  if (!skipLoad) await _loadHistory(sessionId);

  if (window.innerWidth > 768) {
    requestAnimationFrame(() => {
      try { applyEdgeDock(modal, 'right'); } catch (_) {}
    });
  }

  const ta = document.getElementById('split-chat-message');
  if (ta) {
    if (draftMessage) ta.value = String(draftMessage);
    setTimeout(() => ta.focus(), 80);
  }
  return true;
}

export function closeSplit() {
  if (!_open) return;
  _open = false;
  _sessionId = null;
  if (_abort) {
    try { _abort.abort(); } catch (_) {}
    _abort = null;
  }
  _streaming = false;
  document.body.classList.remove('split-chat-active');
  if (_modal) _modal.classList.add('hidden');
  try { Modals.unregister('split-chat-modal'); } catch {}
}

export async function toggleSplit(sessionId) {
  if (_open && _sessionId === sessionId) {
    closeSplit();
    return false;
  }
  if (_open && sessionId && sessionId !== _sessionId) {
    _sessionId = sessionId;
    await _loadHistory(sessionId);
    return true;
  }
  return openSplit(sessionId);
}

const splitChatModule = {
  isActive,
  isStreaming,
  getSecondarySessionId,
  getActiveHistoryEl,
  getActiveSessionId,
  openSplit,
  closeSplit,
  toggleSplit,
};

export default splitChatModule;

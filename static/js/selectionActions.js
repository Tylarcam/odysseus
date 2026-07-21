/**
 * Global text-selection toolbar — Handoff, Search, Listen, Cal, Fork, Gen, and Save on readable surfaces.
 * Singleton bar (Notion/Medium pattern): one DOM node, show/hide, pointerdown dismiss.
 */

import uiModule from './ui.js';
import { registerMenuDismiss, dismissOrRemove } from './escMenuStack.js';
import { openCalTargetMenu } from './selectionCalendar.js';
import { openSearchAgentMenu } from './selectionSearch.js';
import { openGenTargetMenu } from './selectionPromptGen.js';

const MIN_CHARS = 8;
const SHOW_DEBOUNCE_MS = 200;
const API_BASE = typeof window !== 'undefined' ? window.location.origin : '';
const PROMPT_TITLE_MAX = 60;

const COMPOSER_SELECTORS = [
  '#message',
  '#split-chat-message',
  '.note-form-body',
  '#research-query',
  '.note-form-content',
  '.note-cl-quickadd-input',
  '.search-input',
  '#search-chat-input',
  '#settings-modal input',
  '#settings-modal textarea',
  '#settings-modal select',
].join(', ');

const EXCLUDED_ANCESTORS = [
  '.selection-action-bar',
  '.note-handoff-menu-dropdown',
  '.selection-handoff-menu',
  '.selection-cal-menu-dropdown',
  '.selection-search-menu-dropdown',
  '.selection-gen-menu-dropdown',
  '.msg-overflow-menu',
  '#slash-autocomplete',
  '.slash-autocomplete-popup',
  '.copy-code',
  '.edit-code',
  '.save-to-note',
].join(', ');

let _mods = null;
let _barEl = null;
let _handoffBtn = null;
let _forkBtn = null;
let _calBtn = null;
let _searchBtn = null;
let _listenBtn = null;
let _genBtn = null;
let _saveBtn = null;
let _closeBar = null;
let _savingPrompt = false;
let _current = null;
let _debounceTimer = null;
let _mirror = null;
let _showGen = 0;
let _hiding = false;
let _initialized = false;
let _visible = false;
let _mouseDrag = false;

function _isComposer(el) {
  if (!el) return false;
  if (el.matches?.(COMPOSER_SELECTORS)) return true;
  if (el.closest?.(COMPOSER_SELECTORS)) return true;
  if (el.closest?.('[contenteditable="true"]')?.matches?.('.composer-input, .note-form-content')) return true;
  return false;
}

function _isExcludedNode(node) {
  if (!node) return true;
  const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  if (!el) return true;
  if (_barEl?.contains(el)) return true;
  if (el.closest?.(EXCLUDED_ANCESTORS)) return true;
  if (_isComposer(el)) return true;
  return false;
}

function _msgRole(msgEl) {
  if (!msgEl) return 'message';
  if (msgEl.classList.contains('msg-user')) return 'user';
  if (msgEl.classList.contains('msg-ai')) return 'assistant';
  const roleEl = msgEl.querySelector('.role');
  return roleEl?.textContent?.trim() || 'message';
}

function _sessionMeta(sessionId) {
  const sm = _mods?.sessionModule || window.sessionModule;
  if (!sessionId || !sm?.getSessions) return null;
  return sm.getSessions().find(s => s.id === sessionId) || null;
}

function _fullKeepCount(historyId = 'chat-history') {
  const box = document.getElementById(historyId);
  return box ? box.querySelectorAll('.msg').length : 0;
}

function _currentSessionId() {
  return _mods?.sessionModule?.getCurrentSessionId?.()
    || window.sessionModule?.getCurrentSessionId?.()
    || null;
}

export function inferSource(node) {
  const el = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  if (!el) {
    return { label: 'Odysseus selection', keepCount: null, sessionId: null, kind: 'fallback' };
  }

  const splitMsg = el.closest('#split-chat-history .msg');
  if (splitMsg) {
    const box = document.getElementById('split-chat-history');
    const msgs = box ? Array.from(box.querySelectorAll('.msg')) : [];
    const idx = msgs.indexOf(splitMsg);
    const sid = _mods?.splitChatModule?.getSecondarySessionId?.()
      || window.splitChatModule?.getSecondarySessionId?.()
      || null;
    const meta = _sessionMeta(sid);
    const role = _msgRole(splitMsg);
    return {
      label: `Split chat ${role}${meta?.name ? ` (${meta.name})` : ''}`,
      keepCount: idx >= 0 ? idx + 1 : _fullKeepCount('split-chat-history'),
      sessionId: sid,
      kind: 'chat-split',
      paneIdx: null,
    };
  }

  const compareMsg = el.closest('.compare-pane .msg');
  if (compareMsg) {
    const pane = compareMsg.closest('.compare-pane');
    const paneIdx = parseInt(pane?.dataset?.pane ?? '-1', 10);
    const history = pane?.querySelector('.chat-history');
    const msgs = history ? Array.from(history.querySelectorAll('.msg')) : [];
    const idx = msgs.indexOf(compareMsg);
    const sid = (paneIdx >= 0 && window.compareModule?.getPaneSessionId)
      ? window.compareModule.getPaneSessionId(paneIdx)
      : _currentSessionId();
    const role = _msgRole(compareMsg);
    return {
      label: `Compare ${role}${paneIdx >= 0 ? ` (pane ${paneIdx + 1})` : ''}`,
      keepCount: idx >= 0 ? idx + 1 : (history ? msgs.length : 0),
      sessionId: sid,
      kind: 'chat-compare',
      paneIdx: paneIdx >= 0 ? paneIdx : null,
    };
  }

  const chatMsg = el.closest('#chat-history .msg');
  if (chatMsg) {
    const box = document.getElementById('chat-history');
    const msgs = box ? Array.from(box.querySelectorAll('.msg')) : [];
    const idx = msgs.indexOf(chatMsg);
    const sid = _currentSessionId();
    const meta = _sessionMeta(sid);
    const role = _msgRole(chatMsg);
    return {
      label: `Chat ${role}${meta?.name ? ` (${meta.name})` : ''}`,
      keepCount: idx >= 0 ? idx + 1 : _fullKeepCount('chat-history'),
      sessionId: sid,
      kind: 'chat',
      paneIdx: null,
    };
  }

  if (el.closest('#doc-editor-wrap') || el.id === 'doc-editor-textarea' || el.closest('#document-modal')) {
    const title = document.getElementById('doc-title-input')?.value?.trim()
      || document.querySelector('#document-modal .doc-tab.active')?.textContent?.trim()
      || 'Document';
    const docId = window.documentModule?.getCurrentDocId?.() || '';
    const sid = _currentSessionId();
    return {
      label: docId ? `Document: ${title} (${docId})` : `Document: ${title}`,
      keepCount: _fullKeepCount('chat-history'),
      sessionId: sid,
      kind: 'document',
      paneIdx: null,
    };
  }

  const noteCard = el.closest('.note-card');
  if (noteCard) {
    const noteId = noteCard.dataset.noteId || '';
    const title = noteCard.querySelector('.note-card-title')?.textContent?.trim() || '(untitled note)';
    return {
      label: noteId ? `Note: ${title} (${noteId})` : `Note: ${title}`,
      keepCount: _fullKeepCount('chat-history'),
      sessionId: _currentSessionId(),
      kind: 'note',
      paneIdx: null,
    };
  }

  const noteReader = el.closest('.note-form-body');
  if (noteReader && !el.closest('.note-form-content')) {
    const title = noteReader.closest('form')?.querySelector('.note-form-title')?.value?.trim()
      || noteReader.closest('.note-form')?.querySelector('.note-form-title')?.value?.trim()
      || 'Note';
    return {
      label: `Note: ${title}`,
      keepCount: _fullKeepCount('chat-history'),
      sessionId: _currentSessionId(),
      kind: 'note',
      paneIdx: null,
    };
  }

  const researchJob = el.closest('.research-job-card');
  if (researchJob || el.closest('#research-pane')) {
    const jobId = researchJob?.dataset?.jobId || researchJob?.getAttribute('data-job-id') || '';
    const query = researchJob?.querySelector('.research-job-query')?.textContent?.trim()
      || document.getElementById('research-query')?.value?.trim()
      || 'Research';
    return {
      label: jobId ? `Research: ${query} (${jobId})` : `Research: ${query}`,
      keepCount: _fullKeepCount('chat-history'),
      sessionId: _currentSessionId(),
      kind: 'research',
      paneIdx: null,
    };
  }

  const emailBody = el.closest('.email-reader-body, .email-window-body, .email-thread-turn-body');
  if (emailBody) {
    const modal = emailBody.closest('.modal');
    const subject = modal?.querySelector('.email-window-subject')?.textContent?.trim()
      || modal?.querySelector('.modal-header h4 span')?.textContent?.trim()
      || modal?.querySelector('.modal-header h4')?.textContent?.trim()
      || 'Email';
    return {
      label: `Email: ${subject}`,
      keepCount: _fullKeepCount('chat-history'),
      sessionId: _currentSessionId(),
      kind: 'email',
      paneIdx: null,
    };
  }

  return {
    label: 'Odysseus selection',
    keepCount: _fullKeepCount('chat-history'),
    sessionId: _currentSessionId(),
    kind: 'fallback',
    paneIdx: null,
  };
}

function _lastMsgInRange(range, historySelector) {
  const box = document.querySelector(historySelector);
  if (!box || !range) return null;
  const msgs = Array.from(box.querySelectorAll('.msg'));
  let last = null;
  for (const msg of msgs) {
    try {
      if (range.intersectsNode(msg)) last = msg;
    } catch (_) {
      if (range.commonAncestorContainer?.contains?.(msg) || msg.contains(range.commonAncestorContainer)) last = msg;
    }
  }
  return last;
}

function _resolveChatKeepCount(range, source) {
  if (source.kind === 'chat') {
    const last = _lastMsgInRange(range, '#chat-history');
    if (last) {
      const msgs = Array.from(document.querySelectorAll('#chat-history .msg'));
      const idx = msgs.indexOf(last);
      if (idx >= 0) return idx + 1;
    }
    return source.keepCount;
  }
  if (source.kind === 'chat-split') {
    const last = _lastMsgInRange(range, '#split-chat-history');
    if (last) {
      const msgs = Array.from(document.querySelectorAll('#split-chat-history .msg'));
      const idx = msgs.indexOf(last);
      if (idx >= 0) return idx + 1;
    }
    return source.keepCount;
  }
  if (source.kind === 'chat-compare' && source.paneIdx != null) {
    const sel = `.compare-pane[data-pane="${source.paneIdx}"] .chat-history`;
    const last = _lastMsgInRange(range, sel);
    if (last) {
      const msgs = Array.from(document.querySelectorAll(`${sel} .msg`));
      const idx = msgs.indexOf(last);
      if (idx >= 0) return idx + 1;
    }
    return source.keepCount;
  }
  return source.keepCount;
}

function _getTextareaSelectionRect(ta) {
  const start = ta.selectionStart ?? 0;
  const end = ta.selectionEnd ?? start;
  if (start === end) return null;

  const style = getComputedStyle(ta);
  if (!_mirror) {
    _mirror = document.createElement('div');
    _mirror.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;white-space:pre-wrap;word-wrap:break-word;overflow:hidden;top:0;left:0;';
    document.body.appendChild(_mirror);
  }
  _mirror.style.font = style.font;
  _mirror.style.padding = style.padding;
  _mirror.style.border = style.border;
  _mirror.style.width = `${ta.clientWidth}px`;
  _mirror.style.letterSpacing = style.letterSpacing;
  _mirror.style.tabSize = style.tabSize;

  const text = ta.value;
  _mirror.textContent = text.substring(0, start);
  const marker = document.createElement('span');
  marker.textContent = text.substring(start, end) || '.';
  _mirror.appendChild(marker);
  const markerRect = marker.getBoundingClientRect();
  const mirrorRect = _mirror.getBoundingClientRect();
  marker.remove();
  _mirror.textContent = '';

  const taRect = ta.getBoundingClientRect();
  const scrollTop = ta.scrollTop;
  const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.4;
  return {
    left: taRect.left + (markerRect.left - mirrorRect.left),
    top: taRect.top + (markerRect.top - mirrorRect.top) - scrollTop + ta.scrollTop,
    width: Math.max(markerRect.width, 4),
    height: Math.max(markerRect.height, lineHeight),
    right: taRect.left + (markerRect.right - mirrorRect.left),
    bottom: taRect.top + (markerRect.bottom - mirrorRect.top) - scrollTop + ta.scrollTop,
  };
}

export function readSelection() {
  const active = document.activeElement;

  if (active?.matches?.('textarea, input[type="text"], input:not([type])')) {
    if (_isComposer(active)) return null;
    const start = active.selectionStart ?? 0;
    const end = active.selectionEnd ?? start;
    if (start === end) return null;
    const text = active.value.substring(start, end).trim();
    if (text.length < MIN_CHARS) return null;
    const source = inferSource(active);
    const rect = _getTextareaSelectionRect(active);
    return { text, anchorEl: active, source, rect, range: null };
  }

  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  if (_isExcludedNode(sel.anchorNode) || _isExcludedNode(sel.focusNode)) return null;

  const text = sel.toString().trim();
  if (text.length < MIN_CHARS) return null;

  let range;
  try {
    range = sel.getRangeAt(0);
  } catch (_) {
    return null;
  }

  const source = inferSource(sel.anchorNode);
  if (source.kind === 'chat' || source.kind === 'chat-split' || source.kind === 'chat-compare') {
    source.keepCount = _resolveChatKeepCount(range, source);
  }

  let rect;
  try {
    rect = range.getBoundingClientRect();
  } catch (_) {
    rect = null;
  }
  if (!rect || (rect.width === 0 && rect.height === 0)) {
    const rects = range.getClientRects();
    rect = rects.length ? rects[rects.length - 1] : null;
  }

  return { text, range, source, rect, anchorEl: null };
}

function _clearNativeSelection(anchorEl) {
  try {
    window.getSelection()?.removeAllRanges?.();
  } catch (_) {}
  if (anchorEl && typeof anchorEl.selectionStart === 'number') {
    const pos = anchorEl.selectionStart;
    try { anchorEl.setSelectionRange(pos, pos); } catch (_) {}
  }
}

function _rectKey(rect) {
  if (!rect) return '';
  return `${Math.round(rect.left)}:${Math.round(rect.top)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;
}

function _selectionKey(sel) {
  if (!sel) return '';
  return `${sel.text}|${_rectKey(sel.rect)}`;
}

function _cancelPendingShow() {
  clearTimeout(_debounceTimer);
  _debounceTimer = null;
}

function _purgeOrphanBars() {
  document.querySelectorAll('.selection-action-bar').forEach((el) => {
    if (el === _barEl) return;
    dismissOrRemove(el);
  });
}

function _teardownDismiss() {
  if (typeof _closeBar === 'function') {
    try { _closeBar(); } catch (_) {}
  }
  _closeBar = null;
}

function _hideBar(opts = {}) {
  if (_hiding) return;
  _hiding = true;
  _showGen += 1;
  _cancelPendingShow();
  _teardownDismiss();
  _purgeOrphanBars();
  if (_barEl) {
    _barEl.classList.add('hidden');
    _barEl.setAttribute('aria-hidden', 'true');
  }
  _visible = false;
  if (opts.clearSelection && _current) {
    _clearNativeSelection(_current.anchorEl);
  }
  _current = null;
  _hiding = false;
}

function _isOutsideInteraction(ev) {
  if (_barEl?.contains(ev.target)) return false;
  const menu = document.querySelector('.note-handoff-menu-dropdown, .selection-handoff-menu, .selection-cal-menu-dropdown, .selection-search-menu-dropdown');
  if (menu?.contains(ev.target)) return false;
  return true;
}

function _positionBar(bar, rect) {
  if (!rect) {
    bar.style.top = '40%';
    bar.style.left = '50%';
    bar.style.transform = 'translate(-50%, -50%)';
    return;
  }
  bar.style.transform = '';
  const pad = 8;
  const barW = bar.offsetWidth || 160;
  const barH = bar.offsetHeight || 36;
  let left = rect.left + rect.width / 2 - barW / 2;
  let top = rect.bottom + pad;
  if (top + barH > window.innerHeight - pad) top = rect.top - barH - pad;
  left = Math.max(pad, Math.min(left, window.innerWidth - barW - pad));
  top = Math.max(pad, Math.min(top, window.innerHeight - barH - pad));
  bar.style.left = `${Math.round(left)}px`;
  bar.style.top = `${Math.round(top)}px`;
}

const _LISTEN_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>';

function _resetListenBtn() {
  if (!_listenBtn) return;
  _listenBtn.innerHTML = `${_LISTEN_ICON}<span>Listen</span>`;
  _listenBtn.classList.remove('playing', 'loading');
  _listenBtn.title = 'Read selection aloud';
}

function _hasBrowserSpeech() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

function _isTtsAvailable() {
  const mgr = window.aiTTSManager;
  if (mgr?.available && mgr._provider !== 'disabled') return true;
  // Browser Web Speech is always a free fallback — same idea as the
  // document-library Listen button when Open Notebook / server TTS is off.
  return _hasBrowserSpeech();
}

function _updateListenState() {
  if (!_listenBtn) return;
  const available = _isTtsAvailable();
  _listenBtn.hidden = !available;
  _listenBtn.disabled = !available;
  if (!available) _resetListenBtn();
}

function _speakWithBrowser(text, btn) {
  return new Promise((resolve, reject) => {
    if (!_hasBrowserSpeech()) {
      reject(new Error('Browser speech not available'));
      return;
    }
    try { window.speechSynthesis.cancel(); } catch {}
    const u = new SpeechSynthesisUtterance(text);
    const finish = () => {
      _resetListenBtn();
      resolve();
    };
    u.onend = finish;
    u.onerror = (e) => {
      _resetListenBtn();
      reject(new Error(e?.error || 'speech error'));
    };
    if (btn) {
      btn.classList.add('playing');
      btn.innerHTML = `${_LISTEN_ICON}<span>Stop</span>`;
      btn.title = 'Stop reading';
    }
    window.speechSynthesis.speak(u);
  });
}

async function _refreshListenAvailability() {
  const mgr = window.aiTTSManager;
  if (mgr) {
    await (mgr._readyPromise || mgr.checkAvailability());
  }
  _updateListenState();
}

function _forkDisabledReason(source) {
  if (window.innerWidth <= 768) return 'Split chat is desktop-only for now';
  const sid = source?.sessionId || _currentSessionId();
  if (!sid) return 'Open a chat session first';
  const splitMod = _mods?.splitChatModule || window.splitChatModule;
  if (splitMod?.isStreaming?.()) return 'Wait for split chat to finish';
  return '';
}

function _updateForkState(source) {
  if (!_forkBtn) return;
  const reason = _forkDisabledReason(source);
  const mobile = window.innerWidth <= 768;
  _forkBtn.classList.toggle('selection-action-fork--mobile-hidden', mobile);
  _forkBtn.hidden = mobile;
  _forkBtn.disabled = !!reason && !mobile;
  _forkBtn.title = reason || 'Fork to split chat';
}

function _wireDismiss() {
  _teardownDismiss();
  if (!_barEl) return;

  let done = false;
  let unreg = () => {};
  const onPointerDown = (ev) => {
    if (!_visible || !_isOutsideInteraction(ev)) return;
    close();
  };
  const close = () => {
    if (done) return;
    done = true;
    document.removeEventListener('pointerdown', onPointerDown, true);
    unreg();
    _hideBar({ clearSelection: true });
  };

  setTimeout(() => {
    if (!done && _visible) document.addEventListener('pointerdown', onPointerDown, true);
  }, 0);
  unreg = registerMenuDismiss(close);
  _closeBar = close;
  _barEl._dismiss = close;
}

function _onHandoffClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection) return;
  const payload = _mods?.handoffModule?.buildHandoffPayloadFromSelection?.({
    text: selection.text,
    source: selection.source,
  });
  if (!payload) return;
  _hideBar();
  const btnRect = _handoffBtn.getBoundingClientRect();
  _mods?.handoffModule?.openHandoffTargetMenu?.(btnRect, payload, {
    selectionText: selection.text,
    selectionSource: selection.source,
  });
}

function _onSearchClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection) return;
  _hideBar();
  const btnRect = _searchBtn.getBoundingClientRect();
  openSearchAgentMenu(btnRect, {
    text: selection.text,
    source: selection.source,
  });
}

function _onCalClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection) return;
  _hideBar();
  const btnRect = _calBtn.getBoundingClientRect();
  openCalTargetMenu(btnRect, {
    text: selection.text,
    source: selection.source,
  });
}

async function _onListenClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection) return;

  const mgr = window.aiTTSManager;

  // Prefer the TTS manager when it's configured; otherwise fall back to
  // browser speechSynthesis so Listen is never a dead grey button.
  if (mgr) {
    await (mgr._readyPromise || mgr.checkAvailability());
    if (mgr.available && mgr._provider !== 'disabled') {
      if (mgr.isPlaying || mgr._processing) {
        mgr.stop();
        _resetListenBtn();
        return;
      }
      mgr.enqueue(selection.text, _listenBtn, _resetListenBtn);
      return;
    }
  }

  if (!_hasBrowserSpeech()) {
    uiModule?.showToast?.('TTS not available — enable it in Settings → Text to Speech');
    _updateListenState();
    return;
  }

  if (window.speechSynthesis.speaking) {
    try { window.speechSynthesis.cancel(); } catch {}
    _resetListenBtn();
    return;
  }

  try {
    await _speakWithBrowser(selection.text, _listenBtn);
  } catch (err) {
    uiModule?.showError?.(err?.message || 'Listen failed');
    _resetListenBtn();
  }
}

function _onGenClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection) return;
  _hideBar();
  const btnRect = _genBtn.getBoundingClientRect();
  openGenTargetMenu(btnRect, {
    text: selection.text,
    source: selection.source,
  });
}

function _titleFromSelection(text) {
  const line = String(text || '')
    .trim()
    .split(/\n/)[0]
    .replace(/\s+/g, ' ')
    .trim();
  if (!line) return 'Untitled prompt';
  if (line.length <= PROMPT_TITLE_MAX) return line;
  return `${line.slice(0, PROMPT_TITLE_MAX - 1).trimEnd()}…`;
}

async function _onSaveClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection?.text?.trim() || _savingPrompt) return;

  const body = selection.text.trim();
  const title = _titleFromSelection(body);
  _savingPrompt = true;
  _saveBtn?.setAttribute('disabled', '');
  _hideBar({ clearSelection: true });

  try {
    const res = await fetch(`${API_BASE}/api/prompts`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body }),
    });
    if (!res.ok) throw new Error(res.statusText || `HTTP ${res.status}`);
    uiModule?.showToast?.(`Saved to Prompts: ${title}`);
  } catch (err) {
    uiModule?.showError?.(err?.message || 'Failed to save prompt');
  } finally {
    _savingPrompt = false;
    _saveBtn?.removeAttribute('disabled');
  }
}

async function _onForkClick(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const selection = _current;
  if (!selection) return;
  const reason = _forkDisabledReason(selection.source);
  _hideBar({ clearSelection: true });
  if (_forkBtn?.disabled) {
    if (reason) uiModule?.showToast?.(reason);
    return;
  }
  const chat = _mods?.chatModule || window.chatModule;
  if (!chat?.forkSelectionToSplit) return;
  await chat.forkSelectionToSplit({
    text: selection.text,
    keepCount: selection.source?.keepCount,
    sessionId: selection.source?.sessionId,
  });
}

function _ensureBar() {
  if (_barEl) return _barEl;

  _barEl = document.createElement('div');
  _barEl.className = 'selection-action-bar hidden';
  _barEl.setAttribute('role', 'toolbar');
  _barEl.setAttribute('aria-label', 'Selection actions');
  _barEl.setAttribute('aria-hidden', 'true');

  _handoffBtn = document.createElement('button');
  _handoffBtn.type = 'button';
  _handoffBtn.className = 'selection-action-btn selection-action-handoff';
  _handoffBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg><span>Handoff</span>';

  _forkBtn = document.createElement('button');
  _forkBtn.type = 'button';
  _forkBtn.className = 'selection-action-btn selection-action-fork';
  _forkBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><path d="M12 15V9M9.5 7.5L7 8.5M14.5 7.5L17 8.5"/></svg><span>Fork</span>';

  _calBtn = document.createElement('button');
  _calBtn.type = 'button';
  _calBtn.className = 'selection-action-btn selection-action-cal';
  _calBtn.title = 'Add to calendar or schedule a task';
  _calBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg><span>Cal</span>';

  _searchBtn = document.createElement('button');
  _searchBtn.type = 'button';
  _searchBtn.className = 'selection-action-btn selection-action-search';
  _searchBtn.title = 'Search the web with a search agent';
  _searchBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><span>Search</span>';

  _listenBtn = document.createElement('button');
  _listenBtn.type = 'button';
  _listenBtn.className = 'selection-action-btn selection-action-listen';
  _resetListenBtn();
  // Enable immediately when the browser can speak — don't wait on the
  // async TTS-manager probe (that was leaving Listen greyed on first paint).
  _updateListenState();

  _genBtn = document.createElement('button');
  _genBtn.type = 'button';
  _genBtn.className = 'selection-action-btn selection-action-gen';
  _genBtn.title = 'Generate a starter prompt from this selection';
  _genBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.287 1.288L3 12l5.8 1.9a2 2 0 0 1 1.288 1.287L12 21l1.9-5.8a2 2 0 0 1 1.287-1.288L21 12l-5.8-1.9a2 2 0 0 1-1.288-1.287Z"/></svg><span>Gen</span>';

  _saveBtn = document.createElement('button');
  _saveBtn.type = 'button';
  _saveBtn.className = 'selection-action-btn selection-action-save';
  _saveBtn.title = 'Quick-save selection to prompt library';
  _saveBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg><span>Save</span>';

  for (const btn of [_handoffBtn, _searchBtn, _listenBtn, _forkBtn, _calBtn, _genBtn, _saveBtn]) {
    btn.addEventListener('mousedown', (e) => e.preventDefault());
  }
  _handoffBtn.addEventListener('click', _onHandoffClick);
  _searchBtn.addEventListener('click', _onSearchClick);
  _listenBtn.addEventListener('click', _onListenClick);
  _forkBtn.addEventListener('click', _onForkClick);
  _calBtn.addEventListener('click', _onCalClick);
  _genBtn.addEventListener('click', _onGenClick);
  _saveBtn.addEventListener('click', _onSaveClick);

  _barEl.appendChild(_handoffBtn);
  _barEl.appendChild(_searchBtn);
  _barEl.appendChild(_listenBtn);
  _barEl.appendChild(_calBtn);
  _barEl.appendChild(_forkBtn);
  _barEl.appendChild(_genBtn);
  _barEl.appendChild(_saveBtn);
  _barEl.addEventListener('mousedown', (e) => e.preventDefault());
  document.body.appendChild(_barEl);
  return _barEl;
}

function _showBar(selection) {
  _purgeOrphanBars();
  _teardownDismiss();

  const bar = _ensureBar();
  _current = selection;
  _updateForkState(selection.source);
  _refreshListenAvailability();

  bar.classList.remove('hidden');
  bar.setAttribute('aria-hidden', 'false');
  _visible = true;
  _positionBar(bar, selection.rect);
  _wireDismiss();
}

function _scheduleShow() {
  _cancelPendingShow();
  const gen = _showGen;
  _debounceTimer = setTimeout(() => {
    _debounceTimer = null;
    if (gen !== _showGen) return;
    const sel = readSelection();
    if (!sel) {
      if (_visible) _hideBar();
      return;
    }
    if (_visible && _current && _selectionKey(_current) === _selectionKey(sel)) {
      _current = sel;
      _updateForkState(sel.source);
      if (sel.rect) _positionBar(_barEl, sel.rect);
      return;
    }
    if (gen !== _showGen) return;
    _showBar(sel);
  }, SHOW_DEBOUNCE_MS);
}

function _onSelectionChange() {
  const sel = readSelection();
  if (!sel) {
    if (_visible) _hideBar();
    _cancelPendingShow();
    return;
  }
  if (_visible) {
    _current = sel;
    _updateForkState(sel.source);
    if (sel.rect) _positionBar(_barEl, sel.rect);
    return;
  }
  if (!_mouseDrag) _scheduleShow();
}

function _onMouseDown(ev) {
  if (ev.target?.closest?.('.selection-action-bar, .note-handoff-menu-dropdown, .selection-handoff-menu, .selection-cal-menu-dropdown, .selection-search-menu-dropdown')) return;
  _mouseDrag = true;
}

function _onMouseUp(ev) {
  _mouseDrag = false;
  if (ev.target?.closest?.('.selection-action-bar, .note-handoff-menu-dropdown, .selection-handoff-menu, .selection-cal-menu-dropdown, .selection-search-menu-dropdown')) return;
  _scheduleShow();
}

function _onScroll() {
  if (_visible) _hideBar();
}

const _SCROLL_ROOTS = [
  '#chat-history',
  '#split-chat-history',
  '#document-modal .modal-body',
  '#notes-modal .modal-body',
  '#research-pane .research-pane-body',
  '.email-reader-body',
  '.email-window-body',
  '.compare-grid',
];

export function initSelectionActions(mods = {}) {
  if (_initialized || window.__selectionActionsInit) return;
  _initialized = true;
  window.__selectionActionsInit = true;
  _mods = mods;
  _ensureBar();
  _refreshListenAvailability();
  window.addEventListener('odysseus:tts-idle', _updateListenState);

  document.addEventListener('mousedown', _onMouseDown, true);
  document.addEventListener('mouseup', _onMouseUp);
  document.addEventListener('selectionchange', _onSelectionChange);

  document.addEventListener('odysseus:modal-opened', () => {
    _hideBar({ clearSelection: true });
  }, { passive: true });

  document.addEventListener('click', (ev) => {
    if (ev.target.closest?.('.list-item[data-session-id]')) {
      _hideBar({ clearSelection: true });
    }
  }, true);

  _SCROLL_ROOTS.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.addEventListener('scroll', _onScroll, { capture: true, passive: true });
    });
  });

  const observer = new MutationObserver(() => {
    _SCROLL_ROOTS.forEach(s => {
      document.querySelectorAll(s).forEach(el => {
        if (el.__selScrollBound) return;
        el.__selScrollBound = true;
        el.addEventListener('scroll', _onScroll, { capture: true, passive: true });
      });
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });

  window.addEventListener('resize', () => {
    if (_visible) _hideBar();
  }, { passive: true });
}

export default { initSelectionActions, readSelection, inferSource };

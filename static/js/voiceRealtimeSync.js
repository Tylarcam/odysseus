// static/js/voiceRealtimeSync.js — mirror realtime transcripts into chat history
import voiceTelemetry from './voiceTelemetry.js';

let _userBubble = null;
let _assistantBubble = null;
let _assistantText = '';
let _persistQueue = Promise.resolve();

function chatApi() {
  return window.chatModule || null;
}

function isAgentBridge() {
  // In agent mode the transcript is submitted through the chat form, which
  // persists via the normal chat pipeline — persisting here would duplicate.
  try {
    const raw = localStorage.getItem('odysseus_toggle_state');
    return raw ? JSON.parse(raw).mode === 'agent' : false;
  } catch (_) {
    return false;
  }
}

async function ensureSessionId() {
  const sm = window.sessionModule;
  if (!sm) return null;
  let sid = sm.getCurrentSessionId?.();
  if (!sid && sm.hasPendingChat?.() && sm.materializePendingSession) {
    const ok = await sm.materializePendingSession().catch(() => false);
    if (ok) sid = sm.getCurrentSessionId?.();
  }
  return sid || null;
}

function persistMessage(role, content, metadata) {
  if (isAgentBridge()) return;
  const text = (content || '').trim();
  if (!text) return;
  // Chain persists so user/assistant turns land in the DB in UI order.
  _persistQueue = _persistQueue
    .then(async () => {
      const sid = await ensureSessionId();
      if (!sid) return;
      const message = {
        role,
        content: text,
        metadata: { source: 'voice-realtime', ...(metadata || {}) },
      };
      const res = await fetch(`/api/session/${sid}/inject_messages`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [message] }),
      });
      if (!res.ok) throw new Error(`persist failed (${res.status})`);
      voiceTelemetry.emit('sync.persisted', { role, chars: text.length });
    })
    .catch((e) => {
      console.warn('voiceRealtimeSync: persist failed', e);
      voiceTelemetry.emit('sync.persist_failed', { role });
    });
}

function renderPlain(el, text) {
  const md = window.markdownModule;
  if (md?.mdToHtml && md?.squashOutsideCode) {
    el.innerHTML = md.mdToHtml(md.squashOutsideCode(text));
  } else {
    el.textContent = text;
  }
}

export function onUserCommitted() {
  const chat = chatApi();
  if (!chat?.addMessage) return;
  chat.hideWelcomeScreen?.();
  _userBubble = chat.addMessage('user', '…', null, { source: 'voice-realtime', pending: true });
  if (_userBubble) _userBubble.classList.add('voice-pending');
  voiceTelemetry.emit('sync.user.pending');
}

export function onUserTranscript(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return;

  if (_userBubble) {
    const body = _userBubble.querySelector('.body');
    if (body) renderPlain(body, trimmed);
    _userBubble.dataset.raw = trimmed;
    _userBubble.classList.remove('voice-pending');
  } else {
    const chat = chatApi();
    if (chat?.addMessage) {
      chat.hideWelcomeScreen?.();
      _userBubble = chat.addMessage('user', trimmed, null, { source: 'voice-realtime' });
    }
  }
  voiceTelemetry.emit('sync.user.done', { chars: trimmed.length });
  persistMessage('user', trimmed);
  _userBubble = null;
}

export function onAssistantStart() {
  _assistantText = '';
  const chat = chatApi();
  if (!chat?.addMessage) return;
  const sid = window.sessionModule?.getCurrentSessionId?.();
  const meta = window.sessionModule?.getSessions?.()?.find((s) => s.id === sid);
  _assistantBubble = chat.addMessage('assistant', '', meta?.model, {
    source: 'voice-realtime',
    streaming: true,
  });
  if (_assistantBubble) _assistantBubble.classList.add('voice-streaming');
  voiceTelemetry.emit('sync.assistant.start');
}

export function onAssistantDelta(delta) {
  if (!delta) return;
  _assistantText += delta;
  if (_assistantBubble) {
    const body = _assistantBubble.querySelector('.body');
    if (body) renderPlain(body, _assistantText);
    _assistantBubble.dataset.raw = _assistantText;
  }
  window.uiModule?.scrollHistory?.();
}

export function onAssistantDone(opts = {}) {
  const cancelled = !!opts.cancelled;
  if (_assistantBubble) {
    _assistantBubble.classList.remove('voice-streaming');
    if (cancelled) {
      _assistantBubble.classList.add('voice-interrupted');
      const body = _assistantBubble.querySelector('.body');
      if (body && _assistantText.trim()) {
        const note = document.createElement('div');
        note.className = 'voice-interrupted-note';
        note.textContent = '[Interrupted]';
        body.appendChild(note);
      }
    }
    _assistantBubble = null;
  }
  const finalText = _assistantText.trim();
  if (finalText) {
    persistMessage('assistant', finalText, cancelled ? { interrupted: true } : undefined);
  }
  _assistantText = '';
  voiceTelemetry.emit('sync.assistant.done', { cancelled });
}

export function discardPendingUser() {
  // Bridge mode renders the user turn via the chat form — drop the
  // placeholder bubble instead of leaving a dangling "…".
  if (_userBubble && _userBubble.classList.contains('voice-pending')) {
    _userBubble.remove();
  }
  _userBubble = null;
}

export function reset() {
  _userBubble = null;
  _assistantBubble = null;
  _assistantText = '';
}

const voiceRealtimeSync = {
  onUserCommitted,
  onUserTranscript,
  onAssistantStart,
  onAssistantDelta,
  onAssistantDone,
  discardPendingUser,
  reset,
};

window.voiceRealtimeSync = voiceRealtimeSync;
export default voiceRealtimeSync;

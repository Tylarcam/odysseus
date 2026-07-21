// static/js/voiceTelemetry.js — structured voice loop observability
const MAX_EVENTS = 100;

const _events = [];
let _turnId = null;
let _turnStart = null;

const STT_DONE_EVENTS = ['stt.final', 'stt.server.done', 'stt.browser.end'];
const TURN_FLUSH_EVENTS = new Set(['response.done', 'tts.idle', 'realtime.reconnect.done']);

function shouldReportToServer() {
  if (isDebug()) return true;
  try {
    if (window.voiceChatModule?.isActive?.()) return true;
    return localStorage.getItem('odysseus_voice_telemetry_server') === '1';
  } catch (_) {
    return false;
  }
}

function maybeFlushTurn(event) {
  if (!TURN_FLUSH_EVENTS.has(event)) return;
  if (!shouldReportToServer()) return;
  queueMicrotask(() => flushTurnToServer());
}

export async function flushTurnToServer() {
  const turnId = _turnId;
  if (!turnId) return null;
  const events = eventsForTurn(turnId);
  if (events.length === 0) return null;

  try {
    const res = await fetch('/api/voice/telemetry', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turns: [{ turnId, events }] }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    document.dispatchEvent(new CustomEvent('odysseus:voice-slo-updated', { detail: data.slo }));
    return data;
  } catch (e) {
    if (isDebug()) console.warn('[voice] telemetry flush failed', e);
    return null;
  }
}
function isDebug() {
  try {
    if (new URLSearchParams(window.location.search).get('voice_debug')) return true;
    return localStorage.getItem('odysseus_voice_debug') === '1';
  } catch (_) {
    return false;
  }
}

function eventsForTurn(turnId) {
  const id = turnId ?? _turnId;
  if (!id) return [];
  return _events.filter((e) => e.turnId === id);
}

function firstElapsed(turnEvents, ...names) {
  for (const name of names) {
    const hit = turnEvents.find((e) => e.event === name);
    if (hit?.elapsedMs != null) return hit.elapsedMs;
  }
  return null;
}

function hasEvent(turnEvents, name) {
  return turnEvents.some((e) => e.event === name);
}

function findEvent(turnEvents, name) {
  return turnEvents.find((e) => e.event === name) || null;
}

function isVoiceChatAwaiting(detail) {
  if (detail?.awaiting === true) return true;
  if (detail?.awaiting === false) return false;
  try {
    const awaiting = window.voiceChatModule?.isAwaitingReply?.();
    if (typeof awaiting === 'boolean') return awaiting;
  } catch (_) { /* ignore */ }
  return null;
}

const FIRST_AUDIO_EVENTS = ['first_audio_out', 'response.first_audio_out'];

function maybeAutoClearTurn(event, detail) {
  if (event !== 'turn.complete' && event !== 'tts.idle') return;
  if (detail?.clearTurn === false) return;

  const awaiting = isVoiceChatAwaiting(detail);
  if (awaiting === true) return;
  if (awaiting === false || detail?.clearTurn === true) {
    if (isDebug()) console.log('[voice]', 'auto clearTurn after', event);
    clearTurn();
  }
}

export function startTurn() {
  _turnId = `v-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  _turnStart = performance.now();
  emit('turn.start');
  return _turnId;
}

let _sourceTag = '';

export function setSource(source) {
  _sourceTag = (source || '').trim();
  return _sourceTag;
}

export function getSource() {
  return _sourceTag;
}

export function emit(event, detail = {}) {
  const entry = {
    ts: Date.now(),
    event,
    turnId: _turnId,
    elapsedMs: _turnStart != null ? Math.round(performance.now() - _turnStart) : null,
    ...(_sourceTag ? { source: _sourceTag } : {}),
    ...detail,
  };
  _events.push(entry);
  if (_events.length > MAX_EVENTS) _events.shift();
  document.dispatchEvent(new CustomEvent('odysseus:voice-telemetry', { detail: entry }));
  if (isDebug()) console.log('[voice]', event, entry);
  maybeAutoClearTurn(event, detail);
  maybeFlushTurn(event);
}

export function getRecentEvents(limit = 20) {
  if (limit == null || limit <= 0 || limit >= _events.length) return [..._events];
  return _events.slice(-limit);
}

export function getCurrentTurnId() {
  return _turnId;
}

function segmentMs(turnEvents, fromEvent, toEvent) {
  const from = turnEvents.find((e) => e.event === fromEvent);
  const to = turnEvents.find((e) => e.event === toEvent);
  if (!from || !to || from.elapsedMs == null || to.elapsedMs == null) return null;
  return to.elapsedMs - from.elapsedMs;
}

export function getTurnLatencies(turnId) {
  const turnEvents = eventsForTurn(turnId);
  if (turnEvents.length === 0) {
    return {
      micStart: null,
      sttDone: null,
      committed: null,
      responseCreated: null,
      firstAudio: null,
      micToFirstAudio: null,
      speechStopToResponse: null,
      ttsIdle: null,
      responseDone: null,
      bargeIn: null,
    };
  }

  const micStart = firstElapsed(turnEvents, 'mic.start', 'turn.start');
  const firstAudio = firstElapsed(turnEvents, ...FIRST_AUDIO_EVENTS);

  return {
    micStart,
    sttDone: firstElapsed(turnEvents, ...STT_DONE_EVENTS),
    committed: firstElapsed(turnEvents, 'turn.committed'),
    responseCreated: firstElapsed(turnEvents, 'response.created'),
    firstAudio,
    micToFirstAudio: micStart != null && firstAudio != null ? firstAudio - micStart : null,
    speechStopToResponse: segmentMs(turnEvents, 'speech.stop', 'response.created'),
    ttsIdle: firstElapsed(turnEvents, 'tts.idle'),
    responseDone: firstElapsed(turnEvents, 'response.done'),
    bargeIn: firstElapsed(turnEvents, 'barge_in'),
  };
}

export function diagnoseTurn(turnId) {
  const id = turnId ?? _turnId;
  if (!id) return '—';

  const turnEvents = eventsForTurn(id);
  if (turnEvents.length === 0) return '—';

  if (hasEvent(turnEvents, 'barge_in')) {
    return 'barge-in OK';
  }
  if (hasEvent(turnEvents, 'stt.empty') && !hasEvent(turnEvents, 'turn.committed')) {
    return 'STT empty';
  }
  if (hasEvent(turnEvents, 'turn.submit.blocked')) {
    return 'chat blocked';
  }
  if (hasEvent(turnEvents, 'loop.stuck')) {
    return 'loop stuck';
  }
  const failed = findEvent(turnEvents, 'turn.failed');
  if (failed?.reason === 'awaiting_timeout') {
    return 'loop stuck';
  }
  if (hasEvent(turnEvents, 'turn.committed') && !hasEvent(turnEvents, 'response.created')) {
    return 'awaiting response';
  }
  if (hasEvent(turnEvents, 'response.created')
    && !FIRST_AUDIO_EVENTS.some((n) => hasEvent(turnEvents, n))) {
    return 'awaiting audio';
  }
  if ((hasEvent(turnEvents, 'realtime.reconnect.start') || hasEvent(turnEvents, 'reconnect.start'))
    && !hasEvent(turnEvents, 'realtime.reconnect.done') && !hasEvent(turnEvents, 'reconnect.success')) {
    return 'reconnecting';
  }
  if (hasEvent(turnEvents, 'realtime.reconnect.exhausted') || hasEvent(turnEvents, 'reconnect.failed')) {
    return 'reconnect failed';
  }
  if (hasEvent(turnEvents, 'tts.idle')) {
    return 'OK';
  }
  const responseDone = findEvent(turnEvents, 'response.done');
  if (responseDone && !responseDone.willPlayTts) {
    return 'OK';
  }

  return '—';
}

export function clearTurn() {
  _turnId = null;
  _turnStart = null;
}

const voiceTelemetry = {
  startTurn,
  emit,
  setSource,
  getSource,
  getRecentEvents,
  getCurrentTurnId,
  getTurnLatencies,
  diagnoseTurn,
  clearTurn,
  flushTurnToServer,
  isDebug,
};
window.voiceTelemetry = voiceTelemetry;
export default voiceTelemetry;

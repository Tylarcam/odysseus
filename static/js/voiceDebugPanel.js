// static/js/voiceDebugPanel.js — Phase 0 voice loop dev dashboard (?voice_debug=1)
import voiceTelemetry from './voiceTelemetry.js';

const MAX_DISPLAY_EVENTS = 20;

const FAILURE_EVENT_RE = /^(stt\.empty|turn\.failed|loop\.stuck|mic\.denied|stt\..*\.failed|reconnect\.failed|reconnect\.attempt_failed)$/;

/** @type {Map<string, number>} turnId → elapsedMs at first TTS audio (from turn start) */
const _firstAudioByTurn = new Map();
/** @type {Map<string, number>} turnId → performance.now() at turn.start */
const _turnStartPerf = new Map();

function renderSlo(container, slo) {
  if (!container) return;
  container.replaceChildren();
  if (!slo) {
    container.textContent = 'SLO: loading…';
    return;
  }

  const mic = slo.mic_to_first_audio || {};
  const healthy = slo.healthy ? 'ok' : 'fail';
  const header = document.createElement('div');
  header.className = `voice-debug-panel__slo-status voice-debug-panel__diag--${healthy}`;
  header.textContent = slo.healthy ? 'SLO: green' : 'SLO: red';
  container.appendChild(header);

  const rows = [
    ['mic→first p50', mic.p50_ms, slo.targets?.mic_to_first_audio_p50_ms],
    ['mic→first p95', mic.p95_ms, slo.targets?.mic_to_first_audio_p95_ms],
  ];
  for (const [label, value, target] of rows) {
    const row = document.createElement('div');
    row.className = 'voice-debug-panel__latency-row';
    const targetText = target != null ? ` / ${Math.round(target)}ms` : '';
    row.innerHTML = `<span class="voice-debug-panel__latency-label">${label}</span><span class="voice-debug-panel__latency-value">${formatMs(value)}${targetText}</span>`;
    container.appendChild(row);
  }

  const jarvis = slo.cmd_jarvis;
  if (jarvis && typeof jarvis === 'object') {
    const jMic = jarvis.mic_to_first_audio || {};
    const jHeader = document.createElement('div');
    jHeader.className = 'voice-debug-panel__latency-row';
    const jHealth =
      jarvis.healthy === true ? 'ok' : jarvis.healthy === false ? 'fail' : 'idle';
    jHeader.innerHTML =
      `<span class="voice-debug-panel__latency-label">Jarvis (${jarvis.ingest_count || 0})</span>` +
      `<span class="voice-debug-panel__latency-value voice-debug-panel__diag--${jHealth}">` +
      `${jarvis.healthy === true ? 'green' : jarvis.healthy === false ? 'red' : 'n/a'}</span>`;
    container.appendChild(jHeader);
    const jRows = [
      ['Jarvis p50', jMic.p50_ms, jarvis.target_p95_ms],
      ['Jarvis p95', jMic.p95_ms, jarvis.target_p95_ms],
    ];
    for (const [label, value, target] of jRows) {
      const row = document.createElement('div');
      row.className = 'voice-debug-panel__latency-row';
      const targetText = target != null ? ` / ${Math.round(target)}ms` : '';
      row.innerHTML = `<span class="voice-debug-panel__latency-label">${label}</span><span class="voice-debug-panel__latency-value">${formatMs(value)}${targetText}</span>`;
      container.appendChild(row);
    }
  }
}

async function fetchServerSlo() {
  try {
    const res = await fetch('/api/voice/slo', { credentials: 'same-origin' });
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}

let _panel = null;
let _collapsed = false;
let _serverSlo = null;

function isFailureEvent(name) {
  return FAILURE_EVENT_RE.test(name || '');
}

function formatMs(ms) {
  if (ms == null || Number.isNaN(ms)) return '—';
  return `${Math.round(ms)}ms`;
}

function findEvent(events, turnId, name) {
  return events.find((e) => e.turnId === turnId && e.event === name);
}

function findSttEnd(events, turnId) {
  const turnEvents = events.filter((e) => e.turnId === turnId);
  const prefer = ['stt.final', 'stt.server.done', 'stt.browser.end', 'stt.empty', 'stt.server.failed'];
  for (const name of prefer) {
    const hit = turnEvents.find((e) => e.event === name);
    if (hit) return hit;
  }
  return null;
}

function deltaMs(from, to) {
  if (!from || !to || from.elapsedMs == null || to.elapsedMs == null) return null;
  return to.elapsedMs - from.elapsedMs;
}

function computeLatencies(events, turnId) {
  const micStart = findEvent(events, turnId, 'mic.start') || findEvent(events, turnId, 'turn.start');
  const sttEnd = findSttEnd(events, turnId);
  const committed = findEvent(events, turnId, 'turn.committed');
  const speechStop = findEvent(events, turnId, 'speech.stop');
  const responseCreated = findEvent(events, turnId, 'response.created');
  const responseDone = findEvent(events, turnId, 'response.done');
  const ttsIdle = findEvent(events, turnId, 'tts.idle');
  const firstAudioEvent = findEvent(events, turnId, 'first_audio_out')
    || findEvent(events, turnId, 'response.first_audio_out');
  const firstAudioElapsed = firstAudioEvent?.elapsedMs ?? _firstAudioByTurn.get(turnId);

  let responseToFirstAudio = null;
  if (responseDone?.elapsedMs != null && firstAudioElapsed != null) {
    responseToFirstAudio = firstAudioElapsed - responseDone.elapsedMs;
  }

  let micToFirstAudio = null;
  if (micStart?.elapsedMs != null && firstAudioElapsed != null) {
    micToFirstAudio = firstAudioElapsed - micStart.elapsedMs;
  }

  return {
    micToStt: deltaMs(micStart, sttEnd),
    sttToCommit: deltaMs(sttEnd, committed),
    commitToResponse: deltaMs(committed, responseDone),
    speechStopToResponse: deltaMs(speechStop, responseCreated),
    micToFirstAudio,
    responseToFirstAudio,
    responseToTtsIdle: deltaMs(responseDone, ttsIdle),
  };
}

function diagnose(events, turnId) {
  if (!turnId) return { label: '—', kind: 'idle' };

  const turnEvents = events.filter((e) => e.turnId === turnId);
  if (turnEvents.length === 0) return { label: '—', kind: 'idle' };

  const last = turnEvents[turnEvents.length - 1];
  const has = (name) => turnEvents.some((e) => e.event === name);

  if (has('loop.stuck')) return { label: 'loop stuck', kind: 'fail' };
  if (has('turn.failed')) return { label: 'loop stuck', kind: 'fail' };
  if (has('reconnect.failed')) return { label: 'reconnect failed', kind: 'fail' };
  if ((has('realtime.reconnect.start') || has('reconnect.start'))
    && !has('realtime.reconnect.done') && !has('reconnect.success')) {
    return { label: 'reconnecting', kind: 'warn' };
  }
  if (has('realtime.reconnect.exhausted')) return { label: 'reconnect failed', kind: 'fail' };
  if (has('turn.submit.blocked')) return { label: 'chat blocked', kind: 'warn' };
  if (has('stt.empty')) return { label: 'STT empty', kind: 'fail' };
  if (turnEvents.some((e) => e.event.startsWith('stt.') && e.event.endsWith('.failed'))) {
    return { label: 'STT failed', kind: 'fail' };
  }
  if (has('mic.denied')) return { label: 'mic denied', kind: 'fail' };

  if (has('turn.committed') && !has('response.done') && !has('turn.failed') && !has('loop.stuck')) {
    return { label: 'awaiting response', kind: 'warn' };
  }

  if (has('response.done') || has('tts.idle') || last.event === 'loop.resume') {
    return { label: 'OK', kind: 'ok' };
  }

  if (last.event === 'mic.start' || last.event === 'turn.start') {
    return { label: 'recording', kind: 'idle' };
  }

  return { label: last.event, kind: 'idle' };
}

function formatEventLine(entry) {
  const elapsed = entry.elapsedMs != null ? `${entry.elapsedMs}ms` : '—';
  const detailKeys = Object.keys(entry).filter(
    (k) => !['ts', 'event', 'turnId', 'elapsedMs'].includes(k),
  );
  const detail = detailKeys.length
    ? ' ' + detailKeys.map((k) => `${k}=${JSON.stringify(entry[k])}`).join(' ')
    : '';
  return `${elapsed} ${entry.event}${detail}`;
}

function renderEvents(container, events) {
  const recent = events.slice(-MAX_DISPLAY_EVENTS);
  container.replaceChildren();
  for (const entry of recent) {
    const li = document.createElement('li');
    li.className = 'voice-debug-panel__event';
    if (isFailureEvent(entry.event)) li.classList.add('voice-debug-panel__event--fail');
    li.textContent = formatEventLine(entry);
    container.appendChild(li);
  }
}

function renderLatencies(container, latencies) {
  const rows = [
    ['mic→STT', latencies.micToStt],
    ['STT→commit', latencies.sttToCommit],
    ['commit→response', latencies.commitToResponse],
    ['speech stop→response', latencies.speechStopToResponse],
    ['mic→first audio', latencies.micToFirstAudio],
    ['response→first audio', latencies.responseToFirstAudio],
    ['response→tts idle', latencies.responseToTtsIdle],
  ];
  container.replaceChildren();
  for (const [label, ms] of rows) {
    const row = document.createElement('div');
    row.className = 'voice-debug-panel__latency-row';
    row.innerHTML = `<span class="voice-debug-panel__latency-label">${label}</span><span class="voice-debug-panel__latency-value">${formatMs(ms)}</span>`;
    container.appendChild(row);
  }
}

function refresh() {
  if (!_panel) return;
  const events = voiceTelemetry.getRecentEvents();
  const turnId = voiceTelemetry.getCurrentTurnId();
  const diag = diagnose(events, turnId);
  const latencies = turnId ? computeLatencies(events, turnId) : {};

  _panel.querySelector('.voice-debug-panel__turn').textContent = turnId ? `turn: ${turnId}` : 'turn: —';

  const diagEl = _panel.querySelector('.voice-debug-panel__diag');
  diagEl.textContent = diag.label;
  diagEl.className = `voice-debug-panel__diag voice-debug-panel__diag--${diag.kind}`;

  renderSlo(_panel.querySelector('.voice-debug-panel__slo'), _serverSlo);
  renderLatencies(_panel.querySelector('.voice-debug-panel__latencies'), latencies);
  renderEvents(_panel.querySelector('.voice-debug-panel__events'), events);
}

async function refreshSloFromServer() {
  _serverSlo = await fetchServerSlo();
  refresh();
}

function onVoiceSpeaking(ev) {
  if (!ev.detail?.active) return;
  const turnId = voiceTelemetry.getCurrentTurnId();
  if (!turnId || _firstAudioByTurn.has(turnId)) return;

  const events = voiceTelemetry.getRecentEvents();
  if (!findEvent(events, turnId, 'response.done')) return;

  const t0 = _turnStartPerf.get(turnId);
  if (t0 == null) return;

  _firstAudioByTurn.set(turnId, Math.round(performance.now() - t0));
  refresh();
}

function onTelemetry(ev) {
  const entry = ev.detail;
  if (!entry) return;

  if (entry.event === 'turn.start' && entry.turnId) {
    _firstAudioByTurn.delete(entry.turnId);
    _turnStartPerf.set(entry.turnId, performance.now());
  }
  refresh();
}

function buildPanel() {
  const panel = document.createElement('div');
  panel.id = 'voice-debug-panel';
  panel.className = 'voice-debug-panel';
  panel.innerHTML = `
    <header class="voice-debug-panel__header">
      <span class="voice-debug-panel__title">Voice debug</span>
      <button type="button" class="voice-debug-panel__toggle" title="Collapse panel" aria-expanded="true">−</button>
    </header>
    <div class="voice-debug-panel__body">
      <div class="voice-debug-panel__meta">
        <span class="voice-debug-panel__turn">turn: —</span>
        <span class="voice-debug-panel__diag voice-debug-panel__diag--idle">—</span>
      </div>
      <div class="voice-debug-panel__slo"></div>
      <div class="voice-debug-panel__latencies"></div>
      <ul class="voice-debug-panel__events"></ul>
    </div>
  `;

  const toggle = panel.querySelector('.voice-debug-panel__toggle');
  toggle.addEventListener('click', () => {
    _collapsed = !_collapsed;
    panel.classList.toggle('is-collapsed', _collapsed);
    toggle.textContent = _collapsed ? '+' : '−';
    toggle.setAttribute('aria-expanded', String(!_collapsed));
    toggle.title = _collapsed ? 'Expand panel' : 'Collapse panel';
  });

  return panel;
}

export function initVoiceDebugPanel() {
  if (!voiceTelemetry.isDebug()) return;
  if (_panel) return;

  _panel = buildPanel();
  document.body.appendChild(_panel);

  document.addEventListener('odysseus:voice-telemetry', onTelemetry);
  document.addEventListener('odysseus:voice-slo-updated', (ev) => {
    _serverSlo = ev.detail || null;
    refresh();
  });
  window.addEventListener('odysseus:voice-speaking', onVoiceSpeaking);

  refreshSloFromServer().catch(() => {});
  refresh();
}

export default { initVoiceDebugPanel };

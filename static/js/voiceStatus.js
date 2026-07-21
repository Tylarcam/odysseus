// static/js/voiceStatus.js — voice mode status pill (listening / thinking / speaking)
const STATE_LABELS = {
  connecting: 'Connecting…',
  reconnecting: 'Reconnecting…',
  listening: 'Listening',
  thinking: 'Thinking…',
  speaking: 'Speaking',
  ready: 'Ready',
};

let _bar = null;
let _stateEl = null;
let _modeActive = false;
let _state = 'ready';
let _realtime = false;

function stripStateClasses() {
  document.body.classList.remove(
    'voice-state-connecting',
    'voice-state-reconnecting',
    'voice-state-listening',
    'voice-state-thinking',
    'voice-state-speaking',
    'voice-state-ready',
  );
}

function applyState(state) {
  _state = state || 'ready';
  stripStateClasses();
  document.body.classList.add(`voice-state-${_state}`);

  if (_bar) {
    _bar.dataset.state = _state;
    _bar.classList.toggle('is-visible', _modeActive);
    _bar.hidden = !_modeActive;
  }
  if (_stateEl) {
    _stateEl.textContent = STATE_LABELS[_state] || STATE_LABELS.ready;
  }
}

export function setVoiceModeActive(active, { realtime = false } = {}) {
  _modeActive = !!active;
  _realtime = !!realtime;
  document.body.classList.toggle('voice-mode-active', _modeActive);
  document.body.classList.toggle('voice-mode-realtime', _modeActive && _realtime);
  document.body.classList.toggle('voice-mode-ptt', _modeActive && !_realtime);

  if (_bar) {
    _bar.classList.toggle('voice-status-bar--enter', _modeActive);
    _bar.classList.toggle('voice-status-bar--exit', !_modeActive);
    _bar.hidden = !_modeActive;
    _bar.classList.toggle('is-visible', _modeActive);
  }

  if (!_modeActive) {
    applyState('ready');
    return;
  }
  if (_state === 'ready') applyState('connecting');
}

export function setVoiceUiState(state) {
  if (!_modeActive && state !== 'connecting' && state !== 'reconnecting') return;
  applyState(state);
}

export function getVoiceUiState() {
  return _state;
}

function onListening(e) {
  const active = !!e.detail?.active;
  if (!_modeActive) return;
  if (active) {
    applyState('listening');
    return;
  }
  if (_state === 'listening') applyState('ready');
}

function onSpeaking(e) {
  const active = !!e.detail?.active;
  if (!_modeActive) return;
  if (active) {
    applyState('speaking');
    return;
  }
  if (_state === 'speaking') applyState(_realtime ? 'ready' : 'ready');
}

function onTelemetry(e) {
  const { event } = e.detail || {};
  if (!_modeActive) return;

  if (event === 'realtime.connect.start') applyState('connecting');
  if (event === 'realtime.connect.done') applyState('ready');
  if (event === 'realtime.reconnect.scheduled') applyState('reconnecting');
  if (event === 'turn.committed' || event === 'response.created') {
    if (_state !== 'speaking' && _state !== 'listening') applyState('thinking');
  }
  if (event === 'stt.server.start' || event === 'stt.browser.end') {
    if (_state !== 'speaking') applyState('thinking');
  }
  if (event === 'speech.start') applyState('listening');
  if (event === 'speech.stop' && _state === 'listening') applyState('thinking');
  if (event === 'response.first_audio_out') applyState('speaking');
  if (event === 'response.done' && _state === 'speaking') applyState('ready');
}

function onVoiceState(e) {
  const state = e.detail?.state;
  if (state) setVoiceUiState(state);
}

export function initVoiceStatus() {
  _bar = document.getElementById('voice-status-bar');
  _stateEl = _bar?.querySelector('.voice-status-bar__state');

  window.addEventListener('odysseus:voice-listening', onListening);
  window.addEventListener('odysseus:voice-speaking', onSpeaking);
  document.addEventListener('odysseus:voice-telemetry', onTelemetry);
  document.addEventListener('odysseus:voice-ui-state', onVoiceState);

  document.addEventListener('odysseus:voice-chat-changed', (e) => {
    setVoiceModeActive(!!e.detail?.active, { realtime: !!e.detail?.realtime });
  });
}

const voiceStatusModule = {
  initVoiceStatus,
  setVoiceModeActive,
  setVoiceUiState,
  getVoiceUiState,
};

export default voiceStatusModule;

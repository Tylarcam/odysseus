// static/js/voiceChat.js — voice conversation: WebRTC realtime (preferred) or PTT fallback
import voiceRecorderModule from './voiceRecorder.js';
import voiceRealtimeModule from './voiceRealtime.js';
import voiceTelemetry from './voiceTelemetry.js';

const STORAGE_KEY = 'odysseus_toggle_state';
const RESUME_DELAY_MS = 600;
const AWAITING_TIMEOUT_MS = 45000;
const LOCAL_VOICE_RECORDING_OPTS = {
  autoStop: true,
  silenceMs: 900,
  initialSilenceMs: 9000,
  maxMs: 45000,
  minSpeechMs: 300,
  streamStt: true,
  leaseMode: 'voice-chat',
};

let _active = false;
let _useRealtime = false;
let _awaitingReply = false;
// Set by cancelTurn: blocks auto-resume from re-arming the mic after a user
// cancel. Cleared on any explicit start (mic tap, space-hold, setActive).
let _resumeSuppressed = false;
let _resumeTimer = null;
let _awaitingWatchdog = null;
let _startRecordingFn = null;
let _sttStats = null;
let _voiceChatEnabled = true;
// When true, chat.js abort-on-streaming continues into a new send (barge-in).
let _voiceBargeSubmit = false;
let _pendingBridgeText = null;
let _bridgeSubmitTimer = null;

function isMobile() {
  return 'ontouchstart' in window || (navigator.maxTouchPoints || 0) > 0;
}

function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function loadToggleState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function saveToggleState(patch) {
  try {
    const state = { ...loadToggleState(), ...patch };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (_) { /* ignore */ }
}

function sttProvider() {
  return _sttStats?.provider || voiceRecorderModule._sttProvider || 'disabled';
}

export async function refreshSttState() {
  try {
    const res = await fetch('/api/stt/stats', { credentials: 'same-origin' });
    if (res.ok) {
      _sttStats = await res.json();
      voiceRecorderModule._sttProvider = _sttStats.provider || 'disabled';
    }
  } catch (e) {
    console.warn('Voice chat: failed to refresh STT stats', e);
  }
  return _sttStats;
}

export async function refreshRealtimeState() {
  const stats = await voiceRealtimeModule.fetchStats();
  _voiceChatEnabled = stats?.voice_chat_enabled !== false;
  return stats;
}

export function isVoiceChatFeatureEnabled() {
  return _voiceChatEnabled !== false;
}

export function isRealtimeActive() {
  return _useRealtime && voiceRealtimeModule.isConnected();
}

export async function getSttBlockReason() {
  await refreshRealtimeState();
  if (!_voiceChatEnabled) {
    return 'Voice chat is disabled in Settings.';
  }
  if (voiceRealtimeModule.isAvailable()) {
    return null;
  }

  await refreshSttState();
  const s = _sttStats || {};
  const provider = s.provider || 'disabled';

  if (s.enabled === false) {
    return 'Speech-to-text is off. Enable STT in Settings → Audio & Voice, or set OPENAI_API_KEY for realtime voice.';
  }
  if (provider === 'disabled') {
    return 'Choose an STT provider (Local or Browser) in Settings → Audio & Voice, or set OPENAI_API_KEY for realtime voice.';
  }
  if (provider === 'browser' && isIOS()) {
    return 'On iPhone/iPad, set STT to Local (Whisper) or set OPENAI_API_KEY for realtime voice.';
  }
  if (!s.available) {
    if (provider === 'local' && s.model_loaded === false) {
      return 'Local Whisper is not available on the server. Install faster-whisper, switch STT to Browser, or set OPENAI_API_KEY for realtime voice.';
    }
    return 'STT is configured but unavailable. Open Settings → Audio & Voice, or set OPENAI_API_KEY for realtime voice.';
  }
  return null;
}

export async function sttReady() {
  const reason = await getSttBlockReason();
  return !reason;
}

function isStreaming() {
  const sendBtn = document.querySelector('.send-btn');
  return sendBtn?.dataset.mode === 'streaming';
}

function syncAutoplay(on) {
  if (!_useRealtime && window.aiTTSManager) window.aiTTSManager.autoPlay = !!on;
  const overflowTts = document.getElementById('overflow-tts-btn');
  const autoplayChk = document.getElementById('tts-ctrl-autoplay');
  if (autoplayChk) autoplayChk.checked = !!on;
  if (overflowTts) overflowTts.classList.toggle('active', !!on);
  saveToggleState({ ttsMode: !!on });
}

function syncUi() {
  const sendBtn = document.querySelector('.send-btn');
  if (sendBtn) {
    sendBtn.classList.toggle('voice-chat-mode', _active);
    sendBtn.classList.toggle('voice-realtime-mode', _useRealtime);
  }
  const chk = document.getElementById('tts-ctrl-voice-chat');
  if (chk) chk.checked = _active;
  if (window._updateSendBtnIcon) window._updateSendBtnIcon();
  document.dispatchEvent(new CustomEvent('odysseus:voice-chat-changed', {
    detail: { active: _active, realtime: _useRealtime },
  }));
}

function clearResumeTimer() {
  if (_resumeTimer) {
    clearTimeout(_resumeTimer);
    _resumeTimer = null;
  }
}

function clearAwaitingWatchdog() {
  if (_awaitingWatchdog) {
    clearTimeout(_awaitingWatchdog);
    _awaitingWatchdog = null;
  }
}

function startAwaitingWatchdog() {
  clearAwaitingWatchdog();
  _awaitingWatchdog = setTimeout(() => {
    _awaitingWatchdog = null;
    if (!_awaitingReply) return;
    voiceTelemetry.emit('loop.stuck', { reason: 'awaiting_timeout' });
    onTurnFailed('awaiting_timeout');
  }, AWAITING_TIMEOUT_MS);
}

function canAutoResume() {
  if (_useRealtime) return false;
  return _active && _awaitingReply && !isStreaming()
    && !voiceRecorderModule.getIsRecording() && sttProvider() !== 'disabled';
}

function canStartLocalListening() {
  return !_useRealtime && _active && !isStreaming()
    && !voiceRecorderModule.getIsRecording() && sttProvider() !== 'disabled';
}

function scheduleAutoResume(opts = {}) {
  const force = !!opts.force;
  if (_useRealtime) return;
  if (_resumeSuppressed) return;
  clearResumeTimer();
  if (!force && !canAutoResume()) return;
  if (force && !canStartLocalListening()) return;

  _resumeTimer = setTimeout(async () => {
    _resumeTimer = null;
    if (!force && !canAutoResume()) return;
    if (force && !canStartLocalListening()) return;
    if (!(await sttReady())) return;
    voiceTelemetry.emit('loop.resume', { force });
    await startLocalListening({ reason: force ? 'force' : 'auto_resume' });
  }, RESUME_DELAY_MS);
}

function localTtsIsSpeaking() {
  const mgr = window.aiTTSManager;
  return !!(mgr && (mgr.isPlaying || mgr._processing));
}

export async function startLocalListening({ interrupt = false, reason = 'manual' } = {}) {
  if (reason === 'manual' || reason === 'space_hold') _resumeSuppressed = false;
  if (_resumeSuppressed) return false;
  if (_useRealtime || !_active) return false;
  if (!canStartLocalListening()) return false;
  if (!(await sttReady())) return false;

  clearResumeTimer();
  clearAwaitingWatchdog();
  _awaitingReply = false;

  if (interrupt && localTtsIsSpeaking()) {
    voiceTelemetry.emit('local_barge_in', { reason });
    window.aiTTSManager.stop();
  }

  document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', { detail: { state: 'listening' } }));
  if (_startRecordingFn) {
    _startRecordingFn(LOCAL_VOICE_RECORDING_OPTS);
    return true;
  }
  return false;
}

function submitMessage(text) {
  const input = document.getElementById('message');
  const form = document.getElementById('chat-form');
  if (!input || !form) return false;
  input.value = text.trim();
  input.dispatchEvent(new Event('input', { bubbles: true }));
  form.requestSubmit();
  return true;
}

function softRearmLocal(reason = 'empty') {
  voiceTelemetry.emit('stt.empty', { transport: 'ptt', reason });
  document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
    detail: { state: 'listening', label: "Didn't catch that — still listening" },
  }));
  if (_active && !_useRealtime) scheduleAutoResume({ force: true });
}

async function onTranscription(text, showToast) {
  const trimmed = (text || '').trim();
  if (!trimmed || /^(um+|uh+|ah+|er+|hmm+|mm+|mhm+|huh+|…+|\.+)$/i.test(trimmed)) {
    softRearmLocal('empty_or_filler');
    return;
  }

  voiceTelemetry.emit('stt.final', { chars: trimmed.length });

  if (_active && !_useRealtime) {
    if (isStreaming()) {
      // Barge-in: stop the current agent turn and send the new utterance.
      voiceTelemetry.emit('turn.barge_submit', { chars: trimmed.length });
      _voiceBargeSubmit = true;
      _awaitingReply = true;
      startAwaitingWatchdog();
      document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', { detail: { state: 'thinking' } }));
      const sent = submitMessage(trimmed);
      if (!sent) {
        _voiceBargeSubmit = false;
        onTurnFailed('submit_failed');
      }
      return;
    }

    _awaitingReply = true;
    startAwaitingWatchdog();
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', { detail: { state: 'thinking' } }));
    if (showToast) showToast('Sending...');
    const sent = submitMessage(trimmed);
    if (!sent) {
      onTurnFailed('submit_failed');
      return;
    }
    voiceTelemetry.emit('turn.committed', { chars: trimmed.length });
    return;
  }

  const input = document.getElementById('message');
  if (!input) return;
  const existing = input.value.trim();
  input.value = existing ? `${existing} ${trimmed}` : trimmed;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.focus();
  if (showToast) showToast('Transcribed');
}

export function isActive() {
  return _active;
}

export function isAwaitingReply() {
  return _awaitingReply;
}

let _bridgeAwaiting = false;

function getLastAssistantText() {
  const bubbles = document.querySelectorAll('#chat-history .msg-ai');
  const last = bubbles[bubbles.length - 1];
  if (!last) return '';
  return (last.dataset?.raw || last.querySelector('.body')?.textContent || '').trim();
}

// ── Bridge streaming speech: speak agent output sentence-by-sentence ──
// Instead of waiting for the full agent run to finish and speaking the whole
// reply at once, complete sentences are queued to the realtime session as
// they stream in, so first audio starts within the first sentence.
const BRIDGE_MIN_SENTENCE_CHARS = 15;
const BRIDGE_SPEAK_WATCHDOG_MS = 30000;

const _bridgeSpeech = {
  started: false,   // at least one sentence was queued this turn
  text: '',         // current round's accumulated raw text
  spoken: 0,        // chars of plain text already queued
  queue: [],
  speaking: false,
  watchdog: null,
};

function bridgePlainText(raw) {
  const noCode = (raw || '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/```[\s\S]*$/g, '');
  const mgr = window.aiTTSManager;
  if (mgr?.extractPlainText) {
    try { return mgr.extractPlainText(noCode); } catch (_) { /* fall through */ }
  }
  return noCode;
}

function bridgeCollectSentences(region) {
  const out = [];
  let start = 0;
  let current = '';
  for (let i = 0; i < region.length; i++) {
    current += region[i];
    const ch = region[i];
    const next = region[i + 1];
    if ((ch === '.' || ch === '!' || ch === '?') && next && /\s/.test(next)) {
      const lastWord = current.trim().split(/\s/).pop() || '';
      if (/^\d+\.$/.test(lastWord)) continue;      // "1." list marker
      if (/^[A-Z][a-z]?\.$/.test(lastWord)) continue; // "Dr." abbreviation
      out.push({ text: current.trim(), advance: i + 1 - start });
      start = i + 1;
      current = '';
    }
  }
  return out;
}

function clearBridgeSpeakWatchdog() {
  if (_bridgeSpeech.watchdog) {
    clearTimeout(_bridgeSpeech.watchdog);
    _bridgeSpeech.watchdog = null;
  }
}

function pumpBridgeSpeech() {
  if (_bridgeSpeech.speaking || _bridgeSpeech.queue.length === 0) return;
  const sentence = _bridgeSpeech.queue.shift();
  const ok = voiceRealtimeModule.speakText(sentence);
  if (!ok) {
    voiceTelemetry.emit('bridge.speak_failed', { chars: sentence.length });
    return;
  }
  _bridgeSpeech.speaking = true;
  clearBridgeSpeakWatchdog();
  // If the realtime response never produces audio (error, filtered), unstick.
  _bridgeSpeech.watchdog = setTimeout(() => {
    _bridgeSpeech.watchdog = null;
    _bridgeSpeech.speaking = false;
    pumpBridgeSpeech();
  }, BRIDGE_SPEAK_WATCHDOG_MS);
}

function resetBridgeSpeech() {
  clearBridgeSpeakWatchdog();
  _bridgeSpeech.started = false;
  _bridgeSpeech.text = '';
  _bridgeSpeech.spoken = 0;
  _bridgeSpeech.queue = [];
  _bridgeSpeech.speaking = false;
}

function enqueueBridgeSentences({ flushTail = false } = {}) {
  const plain = bridgePlainText(_bridgeSpeech.text);
  if (plain.length > _bridgeSpeech.spoken) {
    const region = plain.substring(_bridgeSpeech.spoken);
    if (flushTail) {
      const tail = region.trim();
      if (tail.length >= BRIDGE_MIN_SENTENCE_CHARS) {
        _bridgeSpeech.queue.push(tail);
        _bridgeSpeech.started = true;
      }
      _bridgeSpeech.spoken = plain.length;
    } else {
      let advanced = 0;
      for (const s of bridgeCollectSentences(region)) {
        advanced += s.advance;
        if (s.text.length < BRIDGE_MIN_SENTENCE_CHARS) continue;
        _bridgeSpeech.queue.push(s.text);
        _bridgeSpeech.started = true;
      }
      _bridgeSpeech.spoken += advanced;
    }
  }
  pumpBridgeSpeech();
}

/** Called by chat.js on every stream delta with the round's accumulated text. */
export function onAssistantStreamText(roundText) {
  if (!_active || !_useRealtime || !_bridgeAwaiting) return;
  _bridgeSpeech.text = roundText || '';
  enqueueBridgeSentences();
}

/** Called by chat.js when an agent round ends (new round begins). */
export function onAssistantStreamRoundEnd() {
  if (!_active || !_useRealtime || !_bridgeAwaiting) return;
  enqueueBridgeSentences({ flushTail: true });
  _bridgeSpeech.text = '';
  _bridgeSpeech.spoken = 0;
}

function buildBridgePayload(text) {
  const jarvis = !!voiceRealtimeModule.isJarvisMode?.();
  // Keep the spoken text clean in the chat bubble; short marker biases the
  // agent without dumping a system prompt into the user turn.
  if (jarvis) return `[cmd_jarvis] ${text}`;
  return text;
}

function submitBridgeTurn(text) {
  resetBridgeSpeech();
  _bridgeAwaiting = true;
  _awaitingReply = true;
  startAwaitingWatchdog();
  document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', { detail: { state: 'thinking' } }));
  const jarvis = !!voiceRealtimeModule.isJarvisMode?.();
  const payload = buildBridgePayload(text);
  voiceTelemetry.emit('bridge.submit', {
    chars: text.length,
    source: jarvis ? 'cmd_jarvis' : undefined,
  });
  // Flag is only needed while aborting a mid-stream turn; clear for clean submit.
  const sent = submitMessage(payload);
  _voiceBargeSubmit = false;
  if (!sent) {
    _bridgeAwaiting = false;
    _awaitingReply = false;
    clearAwaitingWatchdog();
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: 'Listening' },
    }));
  }
  return sent;
}

export function onBridgeTranscript(text) {
  if (!_active || !_useRealtime) return;
  const trimmed = (text || '').trim();
  if (!trimmed) {
    voiceTelemetry.emit('stt.empty', { transport: 'realtime', reason: 'bridge_empty' });
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: "Didn't catch that — still listening" },
    }));
    return;
  }

  // If the agent is mid-stream, abort + continue into a new submit (chat.js
  // honors _voiceBargeSubmit so the new utterance is not discarded).
  if (isStreaming() || _bridgeAwaiting) {
    _pendingBridgeText = trimmed;
    _voiceBargeSubmit = true;
    voiceTelemetry.emit('bridge.barge_queue', { chars: trimmed.length });
    if (_bridgeSubmitTimer) clearTimeout(_bridgeSubmitTimer);
    window.chatModule?.abortCurrentRequest?.(true);
    resetBridgeSpeech();
    _bridgeAwaiting = false;
    _bridgeSubmitTimer = setTimeout(() => {
      _bridgeSubmitTimer = null;
      const pending = _pendingBridgeText;
      _pendingBridgeText = null;
      if (!pending || !_active || !_useRealtime) {
        _voiceBargeSubmit = false;
        return;
      }
      _voiceBargeSubmit = true;
      submitBridgeTurn(pending);
    }, 40);
    return;
  }

  _voiceBargeSubmit = false;
  submitBridgeTurn(trimmed);
}

export function isVoiceBargeSubmit() {
  return !!_voiceBargeSubmit;
}

export function consumeVoiceBargeSubmit() {
  const v = !!_voiceBargeSubmit;
  _voiceBargeSubmit = false;
  return v;
}

async function enableRealtime({ showError, showToast } = {}) {
  await refreshRealtimeState();
  if (!_voiceChatEnabled) return false;
  if (!voiceRealtimeModule.isAvailable()) return false;

  try {
    voiceRealtimeModule.setAutoReconnect(true);
    await voiceRealtimeModule.connect();
    _useRealtime = true;
    voiceTelemetry.emit('voice_chat.realtime');
    if (showToast) {
      showToast(isMobile()
        ? 'Realtime voice on — speak naturally, pause when done'
        : 'Realtime voice on — speak naturally', 4000);
    }
    return true;
  } catch (e) {
    voiceTelemetry.emit('realtime.connect.failed', { error: e.message });
    if (showError) showError(e.message || 'Realtime voice connection failed');
    return false;
  }
}

async function disableRealtime() {
  voiceRealtimeModule.setAutoReconnect(false);
  if (_useRealtime || voiceRealtimeModule.isConnected()) {
    await voiceRealtimeModule.disconnect();
  }
  _useRealtime = false;
}

export async function setActive(on, { showError, showToast, autoStart = true } = {}) {
  const want = !!on;
  _resumeSuppressed = false;

  if (!want) {
    await disableRealtime();
    _active = false;
    _awaitingReply = false;
    _bridgeAwaiting = false;
    resetBridgeSpeech();
    clearAwaitingWatchdog();
    clearResumeTimer();
    saveToggleState({ voiceChatMode: false });
    syncUi();
    voiceTelemetry.emit('voice_chat.off');
    return true;
  }

  await refreshRealtimeState();
  if (!_voiceChatEnabled) {
    const msg = 'Voice chat is disabled in Settings.';
    if (showError) showError(msg);
    else if (showToast) showToast(msg, 4000);
    return false;
  }

  const realtimeOk = await enableRealtime({ showError, showToast });
  if (realtimeOk) {
    _active = true;
    // Bridge speaks via Realtime speakText — kill local autoplay to avoid
    // double TTS (chat streamingTTS + bridge sentences).
    if (window.aiTTSManager) window.aiTTSManager.autoPlay = false;
    syncAutoplay(false);
    saveToggleState({ voiceChatMode: true });
    syncUi();
    voiceTelemetry.emit('voice_chat.on', { mode: 'realtime' });
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: 'Listening' },
    }));
    return true;
  }

  const ready = await sttReady();
  if (!ready) {
    const msg = await getSttBlockReason();
    if (showError) showError(msg);
    else if (showToast) showToast(msg, 5000);
    document.dispatchEvent(new CustomEvent('odysseus:stt-blocked', { detail: { message: msg } }));
    return false;
  }

  _active = true;
  _useRealtime = false;
  saveToggleState({ voiceChatMode: true });
  syncAutoplay(true);
  syncUi();
  voiceTelemetry.emit('voice_chat.on', { mode: 'ptt' });
  if (autoStart) {
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', { detail: { state: 'listening' } }));
    scheduleAutoResume({ force: true });
  }

  if (showToast) {
    showToast(isMobile() ? 'Voice chat on — speak, then pause' : 'Voice chat on — speak naturally', 3000);
  }
  return true;
}

export async function toggle({ showError, showToast } = {}) {
  return setActive(!_active, { showError, showToast });
}

export function onAssistantTurnComplete(willPlayTts) {
  if (_useRealtime && _bridgeAwaiting && _active) {
    _bridgeAwaiting = false;
    clearAwaitingWatchdog();
    _awaitingReply = false;
    voiceTelemetry.emit('response.done', { bridge: true });
    // Flush any remaining streamed text; sentences already spoken mid-stream.
    enqueueBridgeSentences({ flushTail: true });
    if (!_bridgeSpeech.started) {
      // Stream hook never fired (e.g. background stream) — speak the full reply.
      const text = getLastAssistantText();
      if (text && voiceRealtimeModule.speakText) {
        voiceRealtimeModule.speakText(text);
      }
    }
    _bridgeSpeech.text = '';
    _bridgeSpeech.spoken = 0;
    _bridgeSpeech.started = false;
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: 'Listening' },
    }));
    return;
  }
  if (_useRealtime || !_active || !_awaitingReply) return;
  clearAwaitingWatchdog();
  voiceTelemetry.emit('response.done', { willPlayTts: !!willPlayTts });
  if (willPlayTts) return;
  scheduleAutoResume();
}

export function onTurnFailed(reason = 'unknown') {
  if (_bridgeAwaiting) {
    _bridgeAwaiting = false;
    resetBridgeSpeech();
    clearAwaitingWatchdog();
    _awaitingReply = false;
    voiceTelemetry.emit('turn.failed', { reason, bridge: true });
    return;
  }
  if (_useRealtime || !_active) return;
  voiceTelemetry.emit('turn.failed', { reason });
  clearAwaitingWatchdog();
  _awaitingReply = false;
  scheduleAutoResume({ force: true });
}

/**
 * User-initiated cancel (Esc): discard the in-progress recording, abort a
 * voice-submitted agent turn, and silence voice-chat speech output. Never
 * submits the transcript. Returns true when something was cancelled.
 */
export function cancelTurn({ reason = 'user_cancel' } = {}) {
  let cancelled = false;

  if (voiceRecorderModule.cancelRecording?.()) cancelled = true;

  if (_awaitingReply || _bridgeAwaiting) {
    window.chatModule?.abortCurrentRequest?.(true);
    cancelled = true;
  }

  if (_active && !_useRealtime && localTtsIsSpeaking()) {
    window.aiTTSManager.stop();
    cancelled = true;
  }

  if (_useRealtime) {
    const rtState = voiceRealtimeModule.getState?.() || {};
    if (rtState.agentSpeaking || _bridgeSpeech.speaking || _bridgeSpeech.queue.length) {
      voiceRealtimeModule.cancelResponse?.();
      cancelled = true;
    }
    resetBridgeSpeech();
  }

  if (!cancelled) return false;

  _awaitingReply = false;
  _bridgeAwaiting = false;
  clearAwaitingWatchdog();
  clearResumeTimer();
  if (!_useRealtime) _resumeSuppressed = true;
  document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
    detail: { state: _useRealtime ? 'listening' : 'standby' },
  }));
  voiceTelemetry.emit('turn.cancelled', { reason });
  return true;
}

export function registerStartRecording(fn) {
  _startRecordingFn = typeof fn === 'function' ? fn : null;
}

async function restoreSavedMode() {
  await Promise.all([refreshSttState(), refreshRealtimeState()]);
  const saved = loadToggleState();
  if (!saved.voiceChatMode) return;

  const ok = await setActive(true, { autoStart: false });
  if (!ok) {
    saveToggleState({ voiceChatMode: false });
    syncUi();
  }
}

export function initVoiceChat() {
  voiceRecorderModule.setTranscriptionHandler(onTranscription);
  restoreSavedMode().catch(() => {});
  voiceRecorderModule.refreshSttProvider?.().then(() => restoreSavedMode()).catch(() => {});

  window.addEventListener('odysseus:tts-idle', () => {
    voiceTelemetry.emit('tts.idle');
    if (_active && !_useRealtime && _awaitingReply) scheduleAutoResume();
  });

  document.addEventListener('odysseus:voice-realtime-disconnected', (ev) => {
    const reason = ev.detail?.reason;
    if (reason === 'user' || !_active) return;
    voiceTelemetry.emit('voice_chat.realtime_lost', { reason });
  });

  document.addEventListener('odysseus:voice-realtime-reconnecting', async () => {
    try {
      const { showToast } = await import('./ui.js');
      showToast?.('Reconnecting voice…', 3000);
    } catch (_) { /* ignore */ }
  });

  document.addEventListener('odysseus:voice-realtime-reconnect-failed', async (ev) => {
    if (!_active) return;
    const msg = 'Voice connection lost — tap voice chat to retry';
    try {
      const { showError } = await import('./ui.js');
      showError?.(msg);
    } catch (_) { /* ignore */ }
    voiceTelemetry.emit('voice_chat.reconnect_exhausted', { reason: ev.detail?.reason });
  });

  document.addEventListener('odysseus:voice-realtime-reconnected', async () => {
    if (!_active) return;
    try {
      const { showToast } = await import('./ui.js');
      showToast?.('Voice reconnected', 2500);
    } catch (_) { /* ignore */ }
  });

  // Bridge speech queue: advance when a spoken sentence finishes; drop
  // pending sentences when the user barges in.
  document.addEventListener('odysseus:voice-realtime-response-done', (ev) => {
    if (!_useRealtime) return;
    _bridgeSpeech.speaking = false;
    clearBridgeSpeakWatchdog();
    if (ev.detail?.cancelled) {
      _bridgeSpeech.queue = [];
      return;
    }
    pumpBridgeSpeech();
  });

  document.addEventListener('odysseus:voice-barge-in', () => {
    resetBridgeSpeech();
  });

  document.addEventListener('odysseus:voice-realtime-disconnected', () => {
    resetBridgeSpeech();
  });

  document.addEventListener('odysseus:voice-realtime-connected', () => {
    if (window._updateSendBtnIcon) window._updateSendBtnIcon();
  });

  document.addEventListener('odysseus:voice-realtime-disconnected', () => {
    if (window._updateSendBtnIcon) window._updateSendBtnIcon();
  });

  document.addEventListener('visibilitychange', () => {
    if (!_active || !_useRealtime) {
      if (document.hidden) clearResumeTimer();
      return;
    }

    if (document.hidden) {
      voiceRealtimeModule.pauseMic();
      return;
    }

    if (voiceRealtimeModule.isConnected()) {
      voiceRealtimeModule.resumeMic();
      return;
    }

    voiceRealtimeModule.reconnect().catch(() => {});
  });
}

const voiceChatModule = {
  initVoiceChat,
  isActive,
  isAwaitingReply,
  isRealtimeActive,
  setActive,
  toggle,
  onAssistantTurnComplete,
  onAssistantStreamText,
  onAssistantStreamRoundEnd,
  onTurnFailed,
  onBridgeTranscript,
  isVoiceBargeSubmit,
  consumeVoiceBargeSubmit,
  cancelTurn,
  registerStartRecording,
  startLocalListening,
  isMobile,
  sttReady,
  refreshSttState,
  refreshRealtimeState,
  getSttBlockReason,
  isVoiceChatFeatureEnabled,
};

window.voiceChatModule = voiceChatModule;
export default voiceChatModule;

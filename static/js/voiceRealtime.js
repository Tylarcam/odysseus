// static/js/voiceRealtime.js — WebRTC session to OpenAI Realtime via Odysseus gateway
import { applySinkToMediaElement } from './audioOutput.js';
import { emitVoiceListening, emitVoiceSpeaking, emitVoiceThinking } from './voiceVisualizer.js';
import voiceTelemetry from './voiceTelemetry.js';
import voiceRealtimeSync from './voiceRealtimeSync.js';
import micLeaseModule from './micLease.js';

const DATA_CHANNEL_LABEL = 'oai-events';
const BARGE_IN_DEBOUNCE_MS = 400;
const HALF_DUPLEX_STORAGE_KEY = 'odysseus_voice_half_duplex';
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 12000];
const MAX_RECONNECT_ATTEMPTS = 6;
const SESSION_TTL_MS = 55 * 60 * 1000;
const KEEPALIVE_STALE_MS = 5 * 60 * 1000;
const KEEPALIVE_CHECK_MS = 30 * 1000;

let _stats = null;
let _connected = false;
let _connecting = false;
let _pc = null;
let _dc = null;
let _localStream = null;
let _remoteAudio = null;
let _agentSpeaking = false;
let _userSpeaking = false;
let _autoReconnect = false;
let _reconnectTimer = null;
let _reconnectAttempts = 0;
let _micPaused = false;
let _halfDuplexOverride = null;
let _agentSpeakStartedAt = 0;
let _sessionExpiryTimer = null;
let _keepaliveTimer = null;
let _lastEventAt = Date.now();

function touchActivity() {
  _lastEventAt = Date.now();
}

function clearSessionTimers() {
  if (_sessionExpiryTimer) {
    clearTimeout(_sessionExpiryTimer);
    _sessionExpiryTimer = null;
  }
  if (_keepaliveTimer) {
    clearInterval(_keepaliveTimer);
    _keepaliveTimer = null;
  }
}

function startSessionTimers() {
  clearSessionTimers();
  touchActivity();
  _sessionExpiryTimer = setTimeout(() => {
    voiceTelemetry.emit('session.expired');
    handleConnectionLost('session_expired');
  }, SESSION_TTL_MS);
  _keepaliveTimer = setInterval(() => {
    if (!_connected) return;
    if (Date.now() - _lastEventAt > KEEPALIVE_STALE_MS) {
      voiceTelemetry.emit('session.stale', { idleMs: Date.now() - _lastEventAt });
      handleConnectionLost('keepalive_stale');
    }
  }, KEEPALIVE_CHECK_MS);
}
let _assistantStreamStarted = false;
let _jarvisMode = false;
let _voiceLocked = false;
let _vaultBriefMarkdown = '';
let _vaultBriefFetchedAt = 0;
const VAULT_BRIEF_STALE_MS = 60_000;
const VOICE_LOCK_SILENCE_MS = 2000;

function isAgentMode() {
  try {
    const raw = localStorage.getItem('odysseus_toggle_state');
    if (!raw) return false;
    return JSON.parse(raw).mode === 'agent';
  } catch (_) {
    return false;
  }
}

function shouldBridgeTranscript() {
  // CMD Jarvis always escalates actions through the agent bridge.
  return isAgentMode() || _jarvisMode;
}

export function setJarvisMode(on) {
  _jarvisMode = !!on;
  if (_jarvisMode) {
    try { voiceTelemetry.setSource?.('cmd_jarvis'); } catch (_) { /* optional */ }
  } else if (!_voiceLocked) {
    try { voiceTelemetry.setSource?.(''); } catch (_) { /* optional */ }
  }
  if (_connected) applyClientSessionPatch();
  return _jarvisMode;
}

export function isJarvisMode() {
  return _jarvisMode;
}

export function setVoiceLock(on) {
  const next = !!on;
  if (next === _voiceLocked) return _voiceLocked;
  _voiceLocked = next;
  voiceTelemetry.emit(_voiceLocked ? 'voice.lock' : 'voice.unlock');
  document.dispatchEvent(new CustomEvent('odysseus:voice-lock', {
    detail: { locked: _voiceLocked },
  }));
  if (_voiceLocked) {
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: 'Voice Locked' },
    }));
  }
  if (_connected) applyClientSessionPatch();
  return _voiceLocked;
}

export function toggleVoiceLock() {
  return setVoiceLock(!_voiceLocked);
}

export function isVoiceLocked() {
  return _voiceLocked;
}

export async function refreshVaultBrief({ force = false } = {}) {
  if (!force && _vaultBriefMarkdown && (Date.now() - _vaultBriefFetchedAt) < VAULT_BRIEF_STALE_MS) {
    return _vaultBriefMarkdown;
  }
  try {
    const res = await fetch('/api/voice/vault-brief', { credentials: 'same-origin' });
    if (!res.ok) return _vaultBriefMarkdown;
    const data = await res.json();
    _vaultBriefMarkdown = (data.markdown || '').trim();
    _vaultBriefFetchedAt = Date.now();
    voiceTelemetry.emit('vault.brief.refresh', { chars: _vaultBriefMarkdown.length });
    return _vaultBriefMarkdown;
  } catch (e) {
    console.warn('Voice realtime: vault brief refresh failed', e);
    return _vaultBriefMarkdown;
  }
}

export function sendEvent(event) {
  if (!_dc || _dc.readyState !== 'open') return false;
  try {
    _dc.send(JSON.stringify(event));
    return true;
  } catch (e) {
    console.warn('Voice realtime: sendEvent failed', e);
    return false;
  }
}

export function cancelResponse() {
  return sendEvent({ type: 'response.cancel' });
}

export function speakText(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return false;
  voiceTelemetry.emit('bridge.speak', { chars: trimmed.length });
  return sendEvent({
    type: 'response.create',
    response: {
      modalities: ['audio', 'text'],
      instructions: `Speak the following naturally and concisely. Do not add preamble or commentary:\n\n${trimmed}`,
    },
  });
}

function applyClientSessionPatch() {
  const agent = shouldBridgeTranscript();
  const td = _stats?.turn_detection || {};
  const silenceMs = _voiceLocked
    ? VOICE_LOCK_SILENCE_MS
    : (td.silence_duration_ms ?? 500);
  const session = {
    modalities: ['text', 'audio'],
    input_audio_transcription: _stats?.input_audio_transcription || { model: 'whisper-1' },
    turn_detection: {
      type: td.type || 'server_vad',
      threshold: td.threshold ?? 0.5,
      prefix_padding_ms: td.prefix_padding_ms ?? 300,
      silence_duration_ms: silenceMs,
      // Voice lock holds the floor; agent bridge also disables auto-response.
      create_response: !_voiceLocked && !agent,
      interrupt_response: !_voiceLocked,
    },
  };
  // Agent / Jarvis bridge mode runs tools through the full agent loop —
  // strip the voice tool set so the realtime model doesn't also try them.
  if (agent) session.tools = [];
  if (_vaultBriefMarkdown) {
    const jarvisLine = _jarvisMode
      ? 'You are Jarvis for Odysseus CMD. Prefer tools; confirm only for destructive sends.\n\n'
      : '';
    session.instructions = (
      `${jarvisLine}${_vaultBriefMarkdown}`
    ).slice(0, 4000);
  }
  sendEvent({
    type: 'session.update',
    session,
  });
  voiceTelemetry.emit('realtime.session.update', {
    agentBridge: agent,
    voiceLock: _voiceLocked,
    jarvis: _jarvisMode,
  });
}

/** Re-apply agent/chat bridge settings after mode toggle while connected. */
export function reapplySessionPatch() {
  if (!_connected) return false;
  applyClientSessionPatch();
  return true;
}

/** Soft-refresh vault brief into the live Realtime session (CMD soft-refresh). */
export async function reapplyVaultBrief({ force = false } = {}) {
  await refreshVaultBrief({ force });
  return reapplySessionPatch();
}

function extractTranscript(event) {
  return (
    event?.transcript
    || event?.item?.input_audio_transcription?.transcript
    || event?.item?.content?.find?.((c) => c.transcript)?.transcript
    || ''
  );
}

/** Empty / filler-only transcripts soft-rearm listening (not a failed turn). */
function isEmptyTranscript(text) {
  const t = (text || '').trim().toLowerCase();
  if (!t || t.length < 2) return true;
  return /^(um+|uh+|ah+|er+|hmm+|mm+|mhm+|huh+|…+|\.+)$/i.test(t);
}

function softRearmListening(reason = 'empty_transcript') {
  setThinking(false);
  emitUiState('listening');
  voiceTelemetry.emit('stt.empty', { transport: 'realtime', reason });
  document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
    detail: { state: 'listening', label: 'Listening' },
  }));
}

function extractDelta(event) {
  return event?.delta || event?.transcript || '';
}

// ── Voice tool calls (OpenAI Realtime function calling) ──
// The model emits response.function_call_arguments.done on the data channel;
// we execute the tool through Odysseus and return the output to the session.
let _pendingToolCalls = 0;

async function handleFunctionCall(event) {
  const name = event?.name || '';
  const callId = event?.call_id || '';
  if (!name || !callId) return;

  let args = {};
  try {
    args = event.arguments ? JSON.parse(event.arguments) : {};
  } catch (_) { /* send empty args; the tool will report what's missing */ }

  _pendingToolCalls += 1;
  setThinking(true);
  voiceTelemetry.emit('tool.call', { tool: name });
  document.dispatchEvent(new CustomEvent('odysseus:voice-tool-call', {
    detail: { tool: name, state: 'start' },
  }));
  const startedAt = performance.now();

  let output;
  // CMD navigate is a client UI side-effect; still validate via API.
  if (name === 'cmd_navigate') {
    try {
      const res = await fetch('/api/voice/cmd-action', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: args.action || '', id: args.id || '' }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        document.dispatchEvent(new CustomEvent('odysseus:cmd-action', {
          detail: { action: data.action, id: data.id || '' },
        }));
        output = `Opened CMD surface: ${data.action}`
          + (data.id ? ` (${data.id})` : '');
      } else {
        output = `Error: ${data.detail?.message || data.error || `cmd-action failed (${res.status})`}`;
      }
    } catch (e) {
      output = `Error: ${e.message || 'cmd-action failed'}`;
    }
  } else {
    try {
      const res = await fetch('/api/voice/tool-call', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, arguments: args, call_id: callId }),
      });
      if (res.ok) {
        const data = await res.json();
        output = data.output || '(no output)';
      } else {
        const err = await res.json().catch(() => ({}));
        output = `Error: ${err.detail?.message || err.detail || `tool call failed (${res.status})`}`;
      }
    } catch (e) {
      output = `Error: ${e.message || 'tool call failed'}`;
    }
  }

  const latencyMs = Math.round(performance.now() - startedAt);
  voiceTelemetry.emit('tool.result', { tool: name, latencyMs, chars: output.length });
  document.dispatchEvent(new CustomEvent('odysseus:voice-tool-call', {
    detail: { tool: name, state: 'done', latencyMs },
  }));

  _pendingToolCalls = Math.max(0, _pendingToolCalls - 1);
  sendEvent({
    type: 'conversation.item.create',
    item: { type: 'function_call_output', call_id: callId, output },
  });
  // One response after all parallel tool calls resolve — a second
  // response.create while one is active errors out.
  if (_pendingToolCalls === 0) {
    sendEvent({ type: 'response.create' });
  }
}

function handleTranscriptionCompleted(event) {
  const text = extractTranscript(event);
  voiceTelemetry.emit('transcript.user', { chars: (text || '').length });

  if (shouldBridgeTranscript()) {
    // Bridge mode: the chat form submit renders + persists the user turn.
    voiceRealtimeSync.discardPendingUser();
    // Cancel any accidental native Realtime reply, then soft-rearm on empty.
    cancelResponse();
    if (isEmptyTranscript(text)) {
      softRearmListening('empty_or_filler');
      return;
    }
    const trimmed = text.trim();
    // Thin Jarvis intent router: spoken CMD shortcuts fire locally first.
    if (_jarvisMode && maybeDispatchCmdShortcut(trimmed)) {
      emitUiState('listening');
      return;
    }
    voiceTelemetry.emit('turn.eager_bridge', { chars: trimmed.length });
    if (window.voiceChatModule?.onBridgeTranscript) {
      window.voiceChatModule.onBridgeTranscript(trimmed);
    }
    return;
  }

  if (isEmptyTranscript(text)) {
    softRearmListening('empty_or_filler');
    return;
  }
  voiceRealtimeSync.onUserTranscript(text);
}

function maybeDispatchCmdShortcut(text) {
  const t = (text || '').toLowerCase().trim();
  if (!t) return false;
  // Upwork Send Pack (Library) — voice open_doc, not only Money Move "do it".
  const SEND_PACK_ID = '4f9a694f-7103-4ced-9798-3a701929bcbe';
  const rules = [
    // Human-gate confirms FIRST — never bridge, never submit/SMTP/CIHR.
    { re: /\bi submitted (the )?nomination\b/, action: 'confirm_grant_packet_sent', confirmSend: true },
    { re: /\bi submitted (the )?(canada )?(impact\+|impact plus)\b/, action: 'confirm_grant_packet_sent', confirmSend: true },
    { re: /\bi sent (the )?(upwork )?(send )?pack\b/, action: 'confirm_pack_sent', confirmSend: true },
    { re: /\bmark (the )?(upwork )?(send )?pack (as )?(done|sent)\b/, action: 'confirm_pack_sent', confirmSend: true },
    { re: /\bcheck off (the )?(upwork )?(send )?pack\b/, action: 'confirm_pack_sent', confirmSend: true },
    { re: /\bi sent proposal (1|one)\b/, action: 'confirm_proposal_sent', confirmSend: true },
    { re: /\bi sent (the )?(npr )?(thank[- ]you)\b/, action: 'confirm_npr_sent', confirmSend: true },
    { re: /\bi sent (the )?npr\b/, action: 'confirm_npr_sent', confirmSend: true },
    { re: /\bmark (the )?(npr )?(thank[- ]you).*(sent|done)\b/, action: 'confirm_npr_sent', confirmSend: true },
    { re: /\b(open|show)\b.*\bagent bin\b/, action: 'agent_bin' },
    { re: /\b(open|show)\b.*\bjobs?\b/, action: 'jobs' },
    { re: /\b(open|show)\b.*\bemail\b/, action: 'email' },
    { re: /\b(open|show)\b.*\bresearch\b/, action: 'research' },
    { re: /\b(open|show)\b.*\bcalendar\b/, action: 'calendar' },
    { re: /\b(open|show)\b.*\b(notes?|todos?)\b/, action: 'notes' },
    { re: /\bopen (the )?(upwork )?(send )?pack\b/, action: 'open_doc', id: SEND_PACK_ID },
    { re: /\bopen (the |that )(document|doc)\b/, action: 'open_doc', id: SEND_PACK_ID },
    { re: /\b(open|show)\b.*\blibrary\b/, action: 'library' },
    { re: /\b(open|show)\b.*\btasks?\b/, action: 'tasks' },
    { re: /\bplan today\b/, action: 'plan_today' },
    { re: /\brefresh (the )?(vault|cmd|hud)\b/, action: 'refresh' },
    // BRIEF ME / Money Move "Do it" — execute the money needle, don't just narrate it.
    { re: /^(ok(ay)?|yes|yeah|yep)?[,.]?\s*((let'?s|lets) )?do (it|that)\b/, action: 'hero_act' },
    { re: /^(take me there|open (the )?gate)\b/, action: 'hero_act' },
  ];
  for (const rule of rules) {
    if (!rule.re.test(t)) continue;
    document.dispatchEvent(new CustomEvent('odysseus:cmd-action', {
      detail: { action: rule.action, id: rule.id || '' },
    }));
    voiceTelemetry.emit('cmd.shortcut', { action: rule.action });
    // Confirm-send never bridges (agent must not SMTP / Upwork-submit).
    if (rule.confirmSend) {
      return true;
    }
    // If the utterance is ONLY a navigate command, don't also bridge.
    // Longer sentences ("open agent bin and summarize…") still bridge.
    const onlyNav = t.length < 48 && !/\band\b|\bthen\b|\btell me\b|\bsummarize\b/.test(t);
    if (onlyNav) {
      speakText(`Opening ${rule.action.replace(/_/g, ' ')}.`);
      return true;
    }
    // Fire UI side-effect, then let the agent handle the rest.
    return false;
  }
  return false;
}

function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function isSafari() {
  return /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
}

function hasWebRTC() {
  return typeof RTCPeerConnection !== 'undefined'
    && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

function sendClientEvent(event) {
  if (!_dc || _dc.readyState !== 'open') return false;
  try {
    _dc.send(JSON.stringify(event));
    return true;
  } catch (e) {
    console.warn('Voice realtime: sendClientEvent failed', e);
    return false;
  }
}

export function isHalfDuplex() {
  if (_halfDuplexOverride != null) return _halfDuplexOverride;
  try {
    return localStorage.getItem(HALF_DUPLEX_STORAGE_KEY) === '1';
  } catch (_) {
    return false;
  }
}

export function setHalfDuplex(on) {
  _halfDuplexOverride = !!on;
  try {
    if (on) localStorage.setItem(HALF_DUPLEX_STORAGE_KEY, '1');
    else localStorage.removeItem(HALF_DUPLEX_STORAGE_KEY);
  } catch (_) { /* ignore */ }
  if (on && _agentSpeaking) pauseMic();
  else if (!on && _micPaused && !_userSpeaking) resumeMic();
}

function isBargeInDebounced() {
  return _agentSpeakStartedAt > 0
    && (performance.now() - _agentSpeakStartedAt) < BARGE_IN_DEBOUNCE_MS;
}

function stopRemotePlayback() {
  if (!_remoteAudio) return;
  _remoteAudio.pause();
  try { _remoteAudio.currentTime = 0; } catch (_) { /* ignore */ }
}

function setAgentSpeaking(active) {
  const wasSpeaking = _agentSpeaking;
  _agentSpeaking = !!active;

  if (active && !wasSpeaking) {
    _agentSpeakStartedAt = performance.now();
    if (isHalfDuplex()) pauseMic();
    setThinking(false);
    emitVoiceSpeaking(true, _remoteAudio);
    emitUiState('speaking');
    return;
  }

  if (!active && wasSpeaking) {
    _agentSpeakStartedAt = 0;
    emitVoiceSpeaking(false);
    if (isHalfDuplex() && !_userSpeaking) resumeMic();
  }
}

function performBargeIn() {
  const startedAt = performance.now();
  stopRemotePlayback();
  const cancelled = sendClientEvent({ type: 'response.cancel' });
  const cleared = sendClientEvent({ type: 'output_audio_buffer.clear' });
  setAgentSpeaking(false);
  _assistantStreamStarted = false;
  setThinking(false);
  voiceRealtimeSync.onAssistantDone({ cancelled: true });
  emitUiState('listening');
  if (isHalfDuplex()) resumeMic();

  const latencyMs = Math.round(performance.now() - startedAt);
  voiceTelemetry.emit('barge_in', { latencyMs, cancelled, cleared });
  document.dispatchEvent(new CustomEvent('odysseus:voice-barge-in', {
    detail: { latencyMs, cancelled, cleared },
  }));
}

function emitUiState(state) {
  document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', { detail: { state } }));
}

function clearReconnectTimer() {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
}

export async function fetchStats() {
  try {
    const res = await fetch('/api/voice/stats', { credentials: 'same-origin' });
    if (!res.ok) {
      _stats = { available: false };
      return _stats;
    }
    _stats = await res.json();
    return _stats;
  } catch (e) {
    console.warn('Voice realtime: stats fetch failed', e);
    _stats = { available: false };
    return _stats;
  }
}

export function isAvailable() {
  if (_stats?.voice_chat_enabled === false) return false;
  return !!(_stats?.available) && hasWebRTC() && window.isSecureContext;
}

export function isConnected() {
  return _connected;
}

export function getState() {
  return {
    connected: _connected,
    connecting: _connecting,
    userSpeaking: _userSpeaking,
    agentSpeaking: _agentSpeaking,
    autoReconnect: _autoReconnect,
    reconnectAttempts: _reconnectAttempts,
    stats: _stats,
  };
}

function setThinking(active) {
  emitVoiceThinking(!!active);
  if (active) emitUiState('thinking');
}

async function unlockRemotePlayback(audioEl) {
  if (!audioEl) return;
  await applySinkToMediaElement(audioEl).catch(() => {});
  try {
    await audioEl.play();
  } catch (_) {
    // iOS Safari may block until a user gesture — connect() is gesture-initiated.
  }
}

function mapServerEvent(event) {
  touchActivity();
  const type = event?.type || '';
  voiceTelemetry.emit('realtime.event', { type });

  if (type === 'input_audio_buffer.speech_started') {
    const agentWasSpeaking = _agentSpeaking;
    const shouldBargeIn = agentWasSpeaking && !isBargeInDebounced() && !isHalfDuplex();

    if (shouldBargeIn) {
      performBargeIn();
    } else if (agentWasSpeaking && isBargeInDebounced()) {
      voiceTelemetry.emit('barge_in.debounced');
      return;
    }

    _userSpeaking = true;
    setThinking(false);
    if (!agentWasSpeaking || shouldBargeIn) {
      emitVoiceSpeaking(false);
      emitVoiceListening(true, _localStream);
    }
    voiceTelemetry.emit('speech.start');
    emitUiState('listening');
    document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-user-speaking', { detail: { active: true } }));
    return;
  }

  if (type === 'input_audio_buffer.speech_stopped') {
    _userSpeaking = false;
    if (!_agentSpeaking) emitVoiceListening(false);
    voiceTelemetry.emit('speech.stop');
    setThinking(true);
    // Eager signal: with server_vad the buffer auto-commits; mark the turn
    // boundary immediately so telemetry / HUD don't wait on whisper polish.
    if (shouldBridgeTranscript()) {
      voiceTelemetry.emit('turn.commit_pending', { transport: 'realtime', bridge: true });
    }
    document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-user-speaking', { detail: { active: false } }));
    return;
  }

  if (type === 'input_audio_buffer.committed') {
    voiceTelemetry.emit('turn.committed', { transport: 'realtime' });
    // Bridge mode renders the user turn via the chat form submit.
    if (!shouldBridgeTranscript()) voiceRealtimeSync.onUserCommitted();
    setThinking(true);
    return;
  }

  if (
    type === 'conversation.item.input_audio_transcription.completed'
    || type === 'conversation.item.input_audio_transcription.done'
  ) {
    handleTranscriptionCompleted(event);
    return;
  }

  if (type === 'response.function_call_arguments.done') {
    // Agent mode routes tools through the agent loop instead.
    if (!shouldBridgeTranscript()) handleFunctionCall(event);
    return;
  }

  if (type === 'conversation.item.created') {
    voiceTelemetry.emit('conversation.item.created', { item: event.item?.type });
    return;
  }

  if (type === 'response.created') {
    _assistantStreamStarted = false;
    voiceTelemetry.emit('response.created');
    setThinking(true);
    return;
  }

  const transcriptDeltaTypes = new Set([
    'response.audio_transcript.delta',
    'response.output_audio_transcript.delta',
  ]);
  if (transcriptDeltaTypes.has(type)) {
    // Bridge mode: the chat SSE stream already renders the assistant reply;
    // these deltas are just the TTS echo of speakText — don't mirror them.
    if (shouldBridgeTranscript()) return;
    const delta = extractDelta(event);
    if (!_assistantStreamStarted) {
      _assistantStreamStarted = true;
      voiceRealtimeSync.onAssistantStart();
    }
    voiceRealtimeSync.onAssistantDelta(delta);
    return;
  }

  const audioDeltaTypes = new Set([
    'response.output_audio.delta',
    'response.audio.delta',
    'output_audio_buffer.started',
  ]);
  if (audioDeltaTypes.has(type) && !_agentSpeaking) {
    setAgentSpeaking(true);
    voiceTelemetry.emit('response.first_audio_out');
    voiceTelemetry.emit('first_audio_out', { transport: 'realtime' });
  }

  const audioDoneTypes = new Set([
    'response.done',
    'response.output_audio.done',
    'response.audio.done',
    'output_audio_buffer.stopped',
    'response.cancelled',
  ]);
  if (audioDoneTypes.has(type)) {
    const wasSpeaking = _agentSpeaking;
    const cancelled = type === 'response.cancelled'
      || (type === 'response.done' && event.response?.status === 'cancelled');
    setAgentSpeaking(false);
    _assistantStreamStarted = false;
    setThinking(false);
    voiceRealtimeSync.onAssistantDone({ cancelled });
    // Hot mic stays open — show Listening, not standby Ready.
    emitUiState(shouldBridgeTranscript() || _connected ? 'listening' : 'ready');
    voiceTelemetry.emit('response.done', { transport: 'realtime', cancelled });
    if (wasSpeaking || cancelled) {
      document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-response-done', {
        detail: { cancelled },
      }));
    }
  }

  if (type === 'output_audio_buffer.cleared') {
    voiceTelemetry.emit('output_audio_buffer.cleared');
    return;
  }

  if (type === 'error') {
    voiceTelemetry.emit('realtime.error', { error: event.error || event });
  }
}

function wireDataChannel(dc) {
  dc.addEventListener('open', async () => {
    voiceTelemetry.emit('realtime.datachannel.open');
    if (_jarvisMode) {
      await refreshVaultBrief({ force: true });
    }
    applyClientSessionPatch();
  });
  dc.addEventListener('close', () => {
    voiceTelemetry.emit('realtime.datachannel.close');
  });
  dc.addEventListener('message', (e) => {
    try {
      mapServerEvent(JSON.parse(e.data));
    } catch (err) {
      console.warn('Voice realtime: bad event JSON', err);
    }
  });
}

function ensureRemoteAudio() {
  if (_remoteAudio) return _remoteAudio;
  _remoteAudio = document.createElement('audio');
  _remoteAudio.id = 'voice-realtime-audio';
  _remoteAudio.autoplay = true;
  _remoteAudio.playsInline = true;
  _remoteAudio.setAttribute('playsinline', 'true');
  _remoteAudio.style.display = 'none';
  document.body.appendChild(_remoteAudio);
  return _remoteAudio;
}

async function cleanup({ keepReconnect = false } = {}) {
  _connected = false;
  _connecting = false;
  _userSpeaking = false;
  _agentSpeaking = false;
  _micPaused = false;
  _assistantStreamStarted = false;
  _pendingToolCalls = 0;
  if (_voiceLocked) {
    _voiceLocked = false;
    document.dispatchEvent(new CustomEvent('odysseus:voice-lock', {
      detail: { locked: false },
    }));
  }
  voiceRealtimeSync.reset();
  _agentSpeakStartedAt = 0;
  emitVoiceListening(false);
  emitVoiceSpeaking(false);
  setThinking(false);
  clearSessionTimers();

  if (_dc) {
    try { _dc.close(); } catch (_) { /* ignore */ }
    _dc = null;
  }
  if (_pc) {
    try { _pc.close(); } catch (_) { /* ignore */ }
    _pc = null;
  }
  if (_localStream) {
    _localStream.getTracks().forEach((t) => t.stop());
    _localStream = null;
  }
  await micLeaseModule.releaseMicLease();
  if (_remoteAudio) {
    _remoteAudio.pause();
    _remoteAudio.srcObject = null;
  }

  if (!keepReconnect) {
    _autoReconnect = false;
    clearReconnectTimer();
    _reconnectAttempts = 0;
  }
}

function scheduleReconnect() {
  if (!_autoReconnect || _reconnectTimer || _connecting) return;
  if (_reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    voiceTelemetry.emit('realtime.reconnect.exhausted');
    _autoReconnect = false;
    emitUiState('ready');
    document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-reconnect-failed'));
    return;
  }

  const delay = RECONNECT_DELAYS_MS[Math.min(_reconnectAttempts, RECONNECT_DELAYS_MS.length - 1)];
  _reconnectAttempts += 1;
  voiceTelemetry.emit('realtime.reconnect.scheduled', { attempt: _reconnectAttempts, delayMs: delay });
  emitUiState('reconnecting');

  _reconnectTimer = setTimeout(async () => {
    _reconnectTimer = null;
    if (!_autoReconnect) return;
    document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-reconnecting'));
    try {
      await connect({ isReconnect: true });
      _reconnectAttempts = 0;
      document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-reconnected'));
    } catch (e) {
      voiceTelemetry.emit('realtime.reconnect.failed', { error: e.message, attempt: _reconnectAttempts });
      scheduleReconnect();
    }
  }, delay);
}

function handleConnectionLost(reason) {
  if (!_connected && !_connecting) return;
  _connected = false;
  voiceTelemetry.emit('realtime.disconnected', { reason });
  document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-disconnected', {
    detail: { reason },
  }));
  cleanup({ keepReconnect: _autoReconnect }).catch(() => {});
  if (_autoReconnect && reason !== 'user') scheduleReconnect();
}

function buildAudioConstraints() {
  const base = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  if (isIOS() || isSafari()) {
    return { audio: { ...base, channelCount: 1 } };
  }
  return { audio: base };
}

export async function connect({ isReconnect = false } = {}) {
  if (_connected || _connecting) return true;
  if (!window.isSecureContext) {
    throw new Error('Voice realtime requires HTTPS or localhost');
  }
  if (!hasWebRTC()) {
    throw new Error('WebRTC is not supported in this browser');
  }

  await fetchStats();
  if (!isAvailable()) {
    throw new Error('Realtime voice is not available — check OPENAI_API_KEY and Settings');
  }

  _connecting = true;
  if (!isReconnect) voiceTelemetry.startTurn();
  voiceTelemetry.emit(isReconnect ? 'realtime.reconnect.start' : 'realtime.connect.start');
  emitUiState(isReconnect ? 'reconnecting' : 'connecting');

  try {
    const pc = new RTCPeerConnection();
    const audioEl = ensureRemoteAudio();
    let iceRestartAttempted = false;

    pc.ontrack = async (e) => {
      touchActivity();
      const stream = e.streams?.[0];
      if (!stream) return;
      audioEl.srcObject = stream;
      await unlockRemotePlayback(audioEl);
      voiceTelemetry.emit('realtime.remote_track');
    };

    pc.onconnectionstatechange = () => {
      voiceTelemetry.emit('realtime.pc.state', { state: pc.connectionState });
      if (pc.connectionState === 'disconnected' && !iceRestartAttempted && typeof pc.restartIce === 'function') {
        iceRestartAttempted = true;
        try {
          voiceTelemetry.emit('reconnect.ice_restart');
          pc.restartIce();
        } catch (e) {
          voiceTelemetry.emit('reconnect.ice_restart_failed', { error: e.message });
        }
        return;
      }
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
        handleConnectionLost(pc.connectionState);
      }
    };

    pc.oniceconnectionstatechange = () => {
      voiceTelemetry.emit('realtime.ice.state', { state: pc.iceConnectionState });
      if (pc.iceConnectionState === 'failed') {
        handleConnectionLost('ice_failed');
      }
    };

    const leaseStatus = await micLeaseModule.getMicLeaseStatus();
    const busyMsg = micLeaseModule.micBusyMessage(leaseStatus);
    if (busyMsg) {
      throw new Error(busyMsg);
    }
    const lease = await micLeaseModule.claimMicLease('realtime', 600);
    if (!lease.ok) {
      throw new Error(micLeaseModule.micBusyMessage(lease) || 'Microphone is busy');
    }

    const stream = await navigator.mediaDevices.getUserMedia(buildAudioConstraints());
    _localStream = stream;
    stream.getAudioTracks().forEach((track) => pc.addTrack(track, stream));
    voiceTelemetry.emit('mic.start', { transport: 'webrtc' });

    const dc = pc.createDataChannel(DATA_CHANNEL_LABEL);
    wireDataChannel(dc);

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const bridge = shouldBridgeTranscript();
    const sdpRes = await fetch('/api/voice/connect', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/sdp',
        ...(bridge ? { 'X-Voice-Agent-Bridge': '1' } : {}),
      },
      body: offer.sdp,
    });

    if (!sdpRes.ok) {
      const err = await sdpRes.json().catch(() => ({}));
      throw new Error(err.detail?.message || err.detail || `Connect failed (${sdpRes.status})`);
    }

    const answerSdp = await sdpRes.text();
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });

    _pc = pc;
    _dc = dc;
    _connected = true;
    startSessionTimers();
    voiceTelemetry.emit(isReconnect ? 'realtime.reconnect.done' : 'realtime.connect.done');
    emitUiState('ready');
    emitVoiceListening(true, _localStream);
    document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-connected', {
      detail: { reconnect: isReconnect },
    }));
    return true;
  } catch (e) {
    voiceTelemetry.emit('realtime.connect.failed', { error: e.message, reconnect: isReconnect });
    await cleanup({ keepReconnect: _autoReconnect });
    throw e;
  } finally {
    _connecting = false;
  }
}

export async function disconnect() {
  _autoReconnect = false;
  clearReconnectTimer();
  voiceTelemetry.emit('realtime.disconnect');
  await cleanup();
  emitUiState('ready');
  document.dispatchEvent(new CustomEvent('odysseus:voice-realtime-disconnected', { detail: { reason: 'user' } }));
}

export function setAutoReconnect(enabled) {
  _autoReconnect = !!enabled;
  if (!_autoReconnect) {
    clearReconnectTimer();
    _reconnectAttempts = 0;
  }
}

export function setReconnectEnabled(enabled) {
  setAutoReconnect(enabled);
}

export function pauseMic() {
  if (!_localStream || _micPaused) return;
  _localStream.getAudioTracks().forEach((t) => { t.enabled = false; });
  _micPaused = true;
  voiceTelemetry.emit('mic.pause');
}

export function resumeMic() {
  if (!_localStream || !_micPaused) return;
  _localStream.getAudioTracks().forEach((t) => { t.enabled = true; });
  _micPaused = false;
  voiceTelemetry.emit('mic.resume');
}

export async function reconnect() {
  if (_connected || _connecting) return true;
  _autoReconnect = true;
  return connect({ isReconnect: true });
}

export async function tryEnable() {
  try {
    _autoReconnect = true;
    await connect();
    return true;
  } catch (e) {
    console.warn('Voice realtime enable failed:', e.message);
    return false;
  }
}

function onAudioOutputChanged() {
  if (_remoteAudio) applySinkToMediaElement(_remoteAudio).catch(() => {});
}

const voiceRealtimeModule = {
  fetchStats,
  isAvailable,
  isConnected,
  getState,
  connect,
  disconnect,
  tryEnable,
  setAutoReconnect,
  setReconnectEnabled,
  pauseMic,
  resumeMic,
  reconnect,
  setHalfDuplex,
  isHalfDuplex,
  sendEvent,
  cancelResponse,
  speakText,
  reapplySessionPatch,
  reapplyVaultBrief,
  refreshVaultBrief,
  setJarvisMode,
  isJarvisMode,
  setVoiceLock,
  toggleVoiceLock,
  isVoiceLocked,
};

window.addEventListener('odysseus:audio-output-changed', onAudioOutputChanged);
window.voiceRealtimeModule = voiceRealtimeModule;
export default voiceRealtimeModule;

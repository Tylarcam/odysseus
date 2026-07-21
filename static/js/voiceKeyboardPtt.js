/**
 * Hold Space for 3s to start voice recording (VAD auto-stop).
 * While Realtime is live, hold Space to toggle voice lock (hold the floor).
 * Alt+Shift+V arms Jarvis (CMD-style ambient listen) when not typing.
 * Esc cancels the in-flight voice turn (discards — never submits); with a
 * realtime hot mic and nothing in flight, Esc disconnects the voice link.
 * Ignored while typing in inputs/textareas.
 */
import voiceRecorderModule from './voiceRecorder.js';
import voiceChatModule from './voiceChat.js';
import voiceRealtimeModule from './voiceRealtime.js';

const HOLD_MS = 3000;
const LOCK_HOLD_MS = 450;

let _holdTimer = null;
let _holdStartedAt = 0;
let _armed = false;
let _progressEl = null;

function _isTypingTarget(el) {
  if (!el) return false;
  const tag = (el.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.isContentEditable) return true;
  return !!el.closest?.('input, textarea, select, [contenteditable="true"], [contenteditable=""]');
}

function _toast(msg) {
  window.uiModule?.showToast?.(msg);
}

function _showProgress(pct, label = 'Hold to talk') {
  if (!_progressEl) {
    _progressEl = document.createElement('div');
    _progressEl.id = 'voice-ptt-hold-progress';
    _progressEl.setAttribute('aria-hidden', 'true');
    Object.assign(_progressEl.style, {
      position: 'fixed',
      bottom: '24px',
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: '9800',
      minWidth: '180px',
      padding: '10px 14px',
      background: 'rgba(5,10,5,0.92)',
      border: '1px solid rgba(166,226,46,0.45)',
      color: '#a6e22e',
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontSize: '11px',
      letterSpacing: '0.14em',
      textTransform: 'uppercase',
      textAlign: 'center',
      pointerEvents: 'none',
      boxShadow: '0 0 18px rgba(166,226,46,0.2)',
    });
    document.body.appendChild(_progressEl);
  }
  const bar = Math.max(0, Math.min(100, Math.round(pct * 100)));
  _progressEl.textContent = `${label} · ${bar}%`;
  _progressEl.style.display = '';
}

function _hideProgress() {
  if (_progressEl) _progressEl.style.display = 'none';
}

function _clearHold() {
  if (_holdTimer) {
    clearInterval(_holdTimer);
    _holdTimer = null;
  }
  _holdStartedAt = 0;
  _armed = false;
  _hideProgress();
}

async function _armJarvisHotkey() {
  try {
    const cmd = window.cmdCenterModule;
    if (cmd?.openCmdCenter) {
      await cmd.openCmdCenter();
    }
    // Prefer CMD path so vault brief + agent mode apply.
    if (typeof window._cmdActivateVoiceDelegate === 'function') {
      await window._cmdActivateVoiceDelegate();
      return;
    }
    voiceRealtimeModule.setJarvisMode?.(true);
    if (!voiceChatModule.isActive?.()) {
      await voiceChatModule.setActive(true, {
        showError: (m) => window.uiModule?.showError?.(m),
        showToast: (m) => window.uiModule?.showToast?.(m),
        autoStart: true,
      });
    }
    await voiceRealtimeModule.reapplyVaultBrief?.({ force: true });
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: 'Listening' },
    }));
    _toast('Jarvis armed — speak naturally');
  } catch (err) {
    console.warn('[voice-ptt] Jarvis hotkey failed', err);
    _toast('Jarvis arm failed');
  }
}

async function _startVoiceFromHold() {
  _clearHold();

  if (voiceRecorderModule.getIsRecording?.()) return;

  // Realtime mode already streams the mic — toggle voice lock instead.
  if (voiceRealtimeModule.isConnected?.()) {
    const locked = voiceRealtimeModule.toggleVoiceLock?.();
    _toast(locked ? 'Voice lock on — finish your thought' : 'Voice lock off');
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: locked ? 'Voice Locked' : 'Listening' },
    }));
    return;
  }

  try {
    if (!voiceChatModule.isActive?.()) {
      await voiceChatModule.setActive(true, {
        showError: (m) => window.uiModule?.showError?.(m),
        showToast: (m) => window.uiModule?.showToast?.(m),
        autoStart: false,
      });
    }

    // If setActive connected realtime, mic is already hot.
    if (voiceRealtimeModule.isConnected?.()) {
      _toast('Voice link live — speak');
      return;
    }

    const started = await voiceChatModule.startLocalListening({
      interrupt: true,
      reason: 'space_hold',
    });
    if (started) {
      _toast('Listening… (auto-stops on silence)');
    } else {
      // Fallback: one-shot dictation into the chat input.
      const rec = window.voiceRecorderModule || voiceRecorderModule;
      rec.startRecording?.(
        (file) => window.fileHandlerModule?.addFiles?.([file]),
        (m) => window.uiModule?.showToast?.(m),
        (m) => window.uiModule?.showError?.(m),
        { autoStop: true, silenceMs: 900, initialSilenceMs: 9000, maxMs: 45000, minSpeechMs: 300 },
      );
      _toast('Listening… (auto-stops on silence)');
    }
  } catch (err) {
    console.warn('[voice-ptt] start failed', err);
    _toast('Voice start failed');
  }
}

function _stopVoice() {
  const vc = window.voiceChatModule || voiceChatModule;

  if (vc.cancelTurn?.({ reason: 'esc' })) {
    _toast('Voice cancelled');
    return true;
  }

  // Nothing in flight. A realtime hot mic is always recording — Esc
  // disconnects it. An idle PTT session keeps Esc free for vault/modals.
  if (vc.isRealtimeActive?.()) {
    vc.setActive(false, { showToast: (m) => window.uiModule?.showToast?.(m) });
    voiceRealtimeModule.setJarvisMode?.(false);
    _toast('Voice link off');
    return true;
  }
  return false;
}

function _onKeyDown(e) {
  // Perplexity-style vault hotkey: Alt+Shift+V
  if (e.altKey && e.shiftKey && (e.code === 'KeyV' || e.key === 'V' || e.key === 'v')) {
    if (_isTypingTarget(e.target)) return;
    e.preventDefault();
    _armJarvisHotkey();
    return;
  }

  if (e.code !== 'Space' && e.key !== ' ') return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (_isTypingTarget(e.target)) return;
  if (e.repeat) return;

  // Esc-stop is handled separately; Space while recording is a no-op (VAD owns stop).
  if (voiceRecorderModule.getIsRecording?.()) return;

  e.preventDefault();
  if (_holdTimer) return;

  _armed = true;
  _holdStartedAt = performance.now();
  const realtimeLive = voiceRealtimeModule.isConnected?.();
  const threshold = realtimeLive ? LOCK_HOLD_MS : HOLD_MS;
  _showProgress(0, realtimeLive ? 'Hold to lock' : 'Hold to talk');
  _holdTimer = setInterval(() => {
    if (!_armed) return;
    const elapsed = performance.now() - _holdStartedAt;
    const pct = elapsed / threshold;
    _showProgress(pct, realtimeLive ? 'Hold to lock' : 'Hold to talk');
    if (elapsed >= threshold) {
      _startVoiceFromHold();
    }
  }, 50);
}

function _onKeyUp(e) {
  if (e.code !== 'Space' && e.key !== ' ') return;
  if (!_armed) return;
  const realtimeLive = voiceRealtimeModule.isConnected?.();
  const threshold = realtimeLive ? LOCK_HOLD_MS : HOLD_MS;
  // Released before threshold — cancel arming.
  if (performance.now() - _holdStartedAt < threshold) {
    _clearHold();
  }
}

function _onKeyDownEsc(e) {
  if (e.key !== 'Escape') return;
  if (_stopVoice()) {
    e.preventDefault();
    e.stopPropagation();
  }
}

export function initVoiceKeyboardPtt() {
  document.addEventListener('keydown', _onKeyDown, true);
  document.addEventListener('keyup', _onKeyUp, true);
  // Capture so we stop recording before CMD Center / modals consume Esc.
  document.addEventListener('keydown', _onKeyDownEsc, true);
}

export default { initVoiceKeyboardPtt };

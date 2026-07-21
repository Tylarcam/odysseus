// static/js/voiceRecorder.js
import { emitVoiceListening } from './voiceVisualizer.js';
import voiceTelemetry from './voiceTelemetry.js';
import sttStreamModule from './sttStream.js';
import micLeaseModule from './micLease.js';

/**
 * Voice recording with optional Speech-to-Text transcription.
 *
 * STT providers:
 *   "disabled"       — record audio as file attachment (original behavior)
 *   "browser"        — use Web Speech API for real-time transcription
 *   "local"          — send recording to server /api/stt/transcribe (Whisper)
 *   "endpoint:<id>"  — send recording to server /api/stt/transcribe (API)
 */

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recordingStartTime = null;
let recordingInterval = null;
let _recordingMimeType = '';
let _recordingExt = 'webm';
let _autoStopTimer = null;
let _autoStopAudioContext = null;
let _autoStopStartedAt = 0;
let _autoStopSpeechAt = 0;
let _autoStopLastVoiceAt = 0;

// Browser STT state
let _recognition = null;
let _browserTranscript = '';

// Cached STT provider — refreshed on settings change
let _sttProvider = 'disabled';
let _sttProviderFetchedAt = 0;
const STT_PROVIDER_STALE_MS = 30000;

// Optional hook — voice chat uses this to auto-send after transcription
let _transcriptionHandler = null;

// Cancel semantics: a user cancel (Esc) discards the take instead of
// transcribing + delivering it. _cancelWhileAcquiring covers the window
// where getUserMedia hasn't resolved yet so isRecording is still false.
let _discardOnStop = false;
let _acquiringMic = false;
let _cancelWhileAcquiring = false;

// Streaming STT (Phase 2) — active only when opts.streamStt is true and
// sttStream.isStreamingSttAvailable() says the provider is "local". Falls
// back to the existing batch MediaRecorder->blob->POST path otherwise, and
// mid-take on any stream error.
let _usingStreamStt = false;

function pickRecordingMimeType() {
  if (typeof MediaRecorder === 'undefined') return { mimeType: '', ext: 'webm' };
  const candidates = [
    { mimeType: 'audio/webm;codecs=opus', ext: 'webm' },
    { mimeType: 'audio/webm', ext: 'webm' },
    { mimeType: 'audio/mp4', ext: 'mp4' },
    { mimeType: 'audio/aac', ext: 'aac' },
    { mimeType: 'audio/ogg;codecs=opus', ext: 'ogg' },
    { mimeType: '', ext: 'webm' },
  ];
  for (const c of candidates) {
    if (!c.mimeType || MediaRecorder.isTypeSupported(c.mimeType)) {
      return c;
    }
  }
  return { mimeType: '', ext: 'webm' };
}

function blobTypeForRecording() {
  return _recordingMimeType || 'audio/webm';
}

function makeAudioFile(audioBlob, prefix = 'voice-message') {
  const type = blobTypeForRecording();
  return new File([audioBlob], `${prefix}-${Date.now()}.${_recordingExt}`, { type });
}

async function refreshSttProvider() {
  try {
    const res = await fetch('/api/stt/stats', { credentials: 'same-origin' });
    if (res.ok) {
      const stats = await res.json();
      _sttProvider = stats.provider || 'disabled';
      _sttProviderFetchedAt = Date.now();
      sttStreamModule.setCachedProvider(_sttProvider);
      if (window._updateSendBtnIcon) window._updateSendBtnIcon();
    }
  } catch (e) {
    console.warn('Failed to fetch STT stats:', e);
  }
}

function _resetRecordingUI() {
  stopAutoStopMonitor();
  isRecording = false;
  emitVoiceListening(false);
  void micLeaseModule.releaseMicLease();
  if (recordingInterval) {
    clearInterval(recordingInterval);
    recordingInterval = null;
  }
  const sendBtn = document.querySelector('.send-btn');
  if (sendBtn) {
    sendBtn.classList.remove('recording');
    sendBtn.dataset.mode = '';
  }
  if (window._updateSendBtnIcon) {
    setTimeout(window._updateSendBtnIcon, 50);
  }
}

function stopAutoStopMonitor() {
  if (_autoStopTimer) {
    clearInterval(_autoStopTimer);
    _autoStopTimer = null;
  }
  if (_autoStopAudioContext) {
    _autoStopAudioContext.close().catch(() => {});
    _autoStopAudioContext = null;
  }
  _autoStopStartedAt = 0;
  _autoStopSpeechAt = 0;
  _autoStopLastVoiceAt = 0;
}

function startAutoStopMonitor(stream, opts = {}) {
  if (!opts.autoStop || typeof AudioContext === 'undefined' && typeof webkitAudioContext === 'undefined') return;

  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  const silenceMs = Math.max(500, Number(opts.silenceMs || 950));
  const initialSilenceMs = Math.max(2500, Number(opts.initialSilenceMs || 9000));
  const minSpeechMs = Math.max(120, Number(opts.minSpeechMs || 300));
  const maxMs = Math.max(5000, Number(opts.maxMs || 45000));
  const threshold = Math.max(0.003, Number(opts.threshold || 0.018));

  try {
    stopAutoStopMonitor();
    const ctx = new AudioContextCtor();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    _autoStopAudioContext = ctx;
    _autoStopStartedAt = performance.now();
    voiceTelemetry.emit('vad.local.start', { silenceMs, threshold });

    _autoStopTimer = setInterval(() => {
      if (!mediaRecorder || mediaRecorder.state !== 'recording') {
        stopAutoStopMonitor();
        return;
      }

      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (let i = 0; i < samples.length; i++) {
        const v = (samples[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / samples.length);
      const now = performance.now();

      if (rms >= threshold) {
        if (!_autoStopSpeechAt) _autoStopSpeechAt = now;
        _autoStopLastVoiceAt = now;
        return;
      }

      const elapsed = now - _autoStopStartedAt;
      const speechMs = _autoStopSpeechAt ? _autoStopLastVoiceAt - _autoStopSpeechAt : 0;
      const trailingSilenceMs = _autoStopLastVoiceAt ? now - _autoStopLastVoiceAt : 0;
      const readyToStop = speechMs >= minSpeechMs && trailingSilenceMs >= silenceMs;
      const gaveUpWaiting = !_autoStopSpeechAt && elapsed >= initialSilenceMs;
      const hitMax = elapsed >= maxMs;

      if (readyToStop || gaveUpWaiting || hitMax) {
        voiceTelemetry.emit('vad.local.stop', {
          reason: readyToStop ? 'silence' : (gaveUpWaiting ? 'initial_silence' : 'max_duration'),
          elapsedMs: Math.round(elapsed),
          speechMs: Math.round(speechMs),
        });
        stopRecording();
      }
    }, 120);
  } catch (e) {
    voiceTelemetry.emit('vad.local.failed', { error: e.message || String(e) });
    stopAutoStopMonitor();
  }
}

function startBrowserSTT() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  _browserTranscript = '';
  _recognition = new SpeechRecognition();
  _recognition.continuous = true;
  _recognition.interimResults = false;
  _recognition.lang = '';

  _recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        _browserTranscript += event.results[i][0].transcript + ' ';
      }
    }
  };

  _recognition.onerror = (e) => {
    voiceTelemetry.emit('stt.browser.error', { error: e.error });
    console.warn('Browser STT error:', e.error);
  };

  _recognition.start();
  voiceTelemetry.emit('stt.browser.start');
}

/**
 * Stop browser STT and wait for onend so final results are not lost.
 */
function stopBrowserSTT() {
  return new Promise((resolve) => {
    if (!_recognition) {
      resolve(_browserTranscript.trim());
      return;
    }

    const rec = _recognition;
    const timeout = setTimeout(() => {
      _recognition = null;
      voiceTelemetry.emit('stt.browser.end', { via: 'timeout' });
      resolve(_browserTranscript.trim());
    }, 2000);

    rec.onend = () => {
      clearTimeout(timeout);
      _recognition = null;
      voiceTelemetry.emit('stt.browser.end', { via: 'onend' });
      resolve(_browserTranscript.trim());
    };

    try {
      rec.stop();
    } catch (e) {
      clearTimeout(timeout);
      _recognition = null;
      voiceTelemetry.emit('stt.browser.end', { via: 'error', error: String(e) });
      resolve(_browserTranscript.trim());
    }
  });
}

async function transcribeOnServer(audioBlob) {
  const formData = new FormData();
  formData.append('file', audioBlob, `audio.${_recordingExt}`);

  const t0 = performance.now();
  voiceTelemetry.emit('stt.server.start', { bytes: audioBlob.size });

  const res = await fetch('/api/stt/transcribe', {
    method: 'POST',
    credentials: 'same-origin',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    voiceTelemetry.emit('stt.server.failed', { ms: Math.round(performance.now() - t0) });
    throw new Error(err.detail?.message || 'Transcription failed');
  }

  const data = await res.json();
  voiceTelemetry.emit('stt.server.done', {
    ms: Math.round(performance.now() - t0),
    chars: (data.text || '').length,
  });
  return data.text || '';
}

function insertTranscription(text, showToast) {
  if (!text) return;
  const input = document.getElementById('message');
  if (!input) return;

  const existing = input.value.trim();
  input.value = existing ? existing + ' ' + text : text;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.focus();
  if (showToast) showToast('Transcribed');
}

async function deliverTranscription(text, showToast) {
  if (!text) return;
  if (_transcriptionHandler) {
    await _transcriptionHandler(text, showToast);
    return;
  }
  insertTranscription(text, showToast);
}

export function setTranscriptionHandler(fn) {
  _transcriptionHandler = typeof fn === 'function' ? fn : null;
}

export async function startRecording(onFileCreated, showToast, showError, opts = {}) {
  voiceTelemetry.startTurn();

  if (!window.isSecureContext) {
    voiceTelemetry.emit('mic.denied', { reason: 'insecure_context' });
    if (showError) showError('Microphone requires HTTPS. Use a reverse proxy with SSL or access via localhost.');
    _resetRecordingUI();
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    voiceTelemetry.emit('mic.denied', { reason: 'unsupported' });
    if (showError) showError('Microphone not supported in this browser.');
    _resetRecordingUI();
    return;
  }

  if (typeof MediaRecorder === 'undefined') {
    voiceTelemetry.emit('mic.denied', { reason: 'no_media_recorder' });
    if (showError) showError('Audio recording is not supported in this browser.');
    _resetRecordingUI();
    return;
  }

  audioChunks = [];
  const picked = pickRecordingMimeType();
  _recordingMimeType = picked.mimeType;
  _recordingExt = picked.ext;
  _discardOnStop = false;
  _cancelWhileAcquiring = false;
  _acquiringMic = true;

  const leaseMode = opts.leaseMode || 'recorder';
  const leaseStatus = await micLeaseModule.getMicLeaseStatus();
  const busyMsg = micLeaseModule.micBusyMessage(leaseStatus);
  if (busyMsg) {
    _acquiringMic = false;
    voiceTelemetry.emit('mic.denied', { reason: 'lease_busy', holder: leaseStatus.holder });
    if (showError) showError(busyMsg);
    _resetRecordingUI();
    return;
  }

  const lease = await micLeaseModule.claimMicLease(leaseMode);
  if (!lease.ok) {
    _acquiringMic = false;
    voiceTelemetry.emit('mic.denied', { reason: lease.reason || 'lease_denied', holder: lease.holder });
    if (showError) {
      showError(micLeaseModule.micBusyMessage(lease) || 'Microphone is busy. Stop Clicky or voice chat and try again.');
    }
    _resetRecordingUI();
    return;
  }

  navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  })
    .then(async stream => {
      _acquiringMic = false;
        if (_cancelWhileAcquiring) {
        _cancelWhileAcquiring = false;
        stream.getTracks().forEach(track => track.stop());
        voiceTelemetry.emit('mic.cancelled', { during: 'acquire' });
        await micLeaseModule.releaseMicLease();
        _resetRecordingUI();
        return;
      }

      // The cached provider can go stale (settings changed elsewhere, or a
      // long time since the last /api/stt/stats fetch) — re-check before
      // committing to a provider path so we don't record only to fail later.
      if (Date.now() - _sttProviderFetchedAt > STT_PROVIDER_STALE_MS) {
        await refreshSttProvider();
      }

      if (_sttProvider === 'browser' && !window.SpeechRecognition && !window.webkitSpeechRecognition) {
        stream.getTracks().forEach(track => track.stop());
        voiceTelemetry.emit('mic.denied', { reason: 'browser_stt_unsupported' });
        if (showError) {
          showError('This browser does not support speech recognition, but STT is set to "Browser" in Settings > Audio & Voice. Switch STT to Local (Whisper) or use a browser that supports Web Speech API.');
        }
        _resetRecordingUI();
        return;
      }

      const recorderOpts = _recordingMimeType ? { mimeType: _recordingMimeType } : {};
      try {
        mediaRecorder = new MediaRecorder(stream, recorderOpts);
      } catch (err) {
        console.warn('MediaRecorder init failed, retrying without mimeType:', err);
        _recordingMimeType = '';
        _recordingExt = 'webm';
        mediaRecorder = new MediaRecorder(stream);
      }

      _usingStreamStt = !!(opts.streamStt && sttStreamModule.isStreamingSttAvailable());
      if (_usingStreamStt) {
        try {
          await sttStreamModule.startStream(stream, {
            onError: (err) => {
              // Mid-take stream failure: fall back to the batch path for
              // this recording instead of losing the take.
              console.warn('Streaming STT error, falling back to batch:', err);
              _usingStreamStt = false;
            },
          });
        } catch (err) {
          console.warn('Streaming STT failed to start, using batch path:', err);
          _usingStreamStt = false;
        }
      }

      mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        voiceTelemetry.emit('mic.stop');

        if (_discardOnStop) {
          _discardOnStop = false;
          audioChunks = [];
          voiceTelemetry.emit('mic.cancelled', { during: 'recording' });
          _resetRecordingUI();
          return;
        }

        if (_usingStreamStt) {
          _usingStreamStt = false;
          try {
            const transcript = await sttStreamModule.stopStream();
            if (transcript) {
              await deliverTranscription(transcript, showToast);
            } else {
              voiceTelemetry.emit('stt.empty', { provider: 'local-stream' });
              if (showToast) showToast('No speech detected');
            }
          } catch (e) {
            console.error('Streaming STT stop error:', e);
            if (showError) showError('Transcription failed: ' + e.message);
          }
          _resetRecordingUI();
          return;
        }

        const audioBlob = new Blob(audioChunks, { type: blobTypeForRecording() });
        const provider = _sttProvider;

        if (provider === 'browser') {
          const transcript = await stopBrowserSTT();
          if (transcript) {
            await deliverTranscription(transcript, showToast);
          } else {
            voiceTelemetry.emit('stt.empty', { provider: 'browser' });
            if (showToast) showToast('No speech detected');
            const audioFile = makeAudioFile(audioBlob);
            if (onFileCreated) onFileCreated(audioFile);
          }
        } else if (provider === 'local' || provider.startsWith('endpoint:')) {
          if (showToast) showToast('Transcribing...', 5000);
          try {
            const transcript = await transcribeOnServer(audioBlob);
            if (transcript) {
              await deliverTranscription(transcript, showToast);
            } else {
              voiceTelemetry.emit('stt.empty', { provider });
              if (showToast) showToast('No speech detected');
            }
          } catch (e) {
            console.error('STT transcription error:', e);
            voiceTelemetry.emit('stt.server.failed', { error: e.message });
            if (showError) showError('Transcription failed: ' + e.message);
            const audioFile = makeAudioFile(audioBlob);
            if (onFileCreated) onFileCreated(audioFile);
          }
        } else {
          const audioFile = makeAudioFile(audioBlob);
          if (onFileCreated) onFileCreated(audioFile);
        }

        _resetRecordingUI();
      };

      mediaRecorder.start(250);
      isRecording = true;
      recordingStartTime = new Date();
      emitVoiceListening(true, stream);
      voiceTelemetry.emit('mic.start', { provider: _sttProvider });
      startAutoStopMonitor(stream, opts);

      if (_sttProvider === 'browser') {
        startBrowserSTT();
      }

      if (showToast) {
        showToast('Recording...');
      }
    })
    .catch(error => {
      _acquiringMic = false;
      _cancelWhileAcquiring = false;
      console.error('Microphone access error:', error);
      voiceTelemetry.emit('mic.denied', { reason: error.name || 'error', message: error.message });
      if (showError) {
        if (error.name === 'NotAllowedError') {
          showError('Microphone access denied. Check browser permissions.');
        } else if (error.name === 'NotFoundError') {
          showError('No microphone found.');
        } else if (error.name === 'NotReadableError' || error.name === 'AbortError') {
          showError('Microphone is busy — release Clicky (Ctrl+Alt) or stop voice chat, then try again.');
        } else {
          showError('Microphone error: ' + error.message);
        }
      }
      _resetRecordingUI();
    });
}

export function stopRecording() {
  stopAutoStopMonitor();
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  } else {
    _resetRecordingUI();
  }
}

/**
 * Stop and discard the in-progress (or still-acquiring) recording —
 * no transcription, no delivery. Returns true if there was a take to cancel.
 */
export function cancelRecording() {
  if (_usingStreamStt) {
    _usingStreamStt = false;
    sttStreamModule.cancelStream();
  }
  if (_acquiringMic) {
    _cancelWhileAcquiring = true;
    return true;
  }
  if (!isRecording && !(mediaRecorder && mediaRecorder.state === 'recording')) {
    return false;
  }
  _discardOnStop = true;
  if (_recognition) {
    const rec = _recognition;
    _recognition = null;
    try { rec.onend = null; rec.abort(); } catch (_) { /* already stopped */ }
  }
  _browserTranscript = '';
  stopRecording();
  return true;
}

export function getIsRecording() {
  return isRecording;
}

export function init() {
  isRecording = false;
  refreshSttProvider();
}

const voiceRecorderModule = {
  startRecording,
  stopRecording,
  cancelRecording,
  getIsRecording,
  init,
  refreshSttProvider,
  setTranscriptionHandler,
  get _sttProvider() { return _sttProvider; },
  set _sttProvider(v) { _sttProvider = v; },
};

export default voiceRecorderModule;

// static/js/sttStream.js — streaming STT client (Phase 2 of the voice rebuild)
//
// Talks to the /api/stt/stream WebSocket: downsamples mic audio to 16kHz
// 16-bit PCM mono and posts binary frames, receiving {partial, final} text
// back. Only used when the server STT provider is "local" (checked via the
// cached /api/stt/stats response voiceRecorder.js already fetches).
import voiceTelemetry from './voiceTelemetry.js';

const TARGET_SAMPLE_RATE = 16000;

let _ws = null;
let _audioContext = null;
let _sourceNode = null;
let _processorNode = null;
let _stream = null;
let _cachedProvider = null;
let _resolveStop = null;
let _callbacks = {};

function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/api/stt/stream`;
}

export function isStreamingSttAvailable() {
  if (typeof WebSocket === 'undefined') return false;
  if (typeof AudioContext === 'undefined' && typeof window.webkitAudioContext === 'undefined') return false;
  return _cachedProvider === 'local';
}

/**
 * Called by voiceRecorder.js whenever it refreshes /api/stt/stats so this
 * module's availability check stays in sync with the same cache.
 */
export function setCachedProvider(provider) {
  _cachedProvider = provider || null;
}

function downsampleTo16kPcm(float32Input, inputSampleRate) {
  if (inputSampleRate === TARGET_SAMPLE_RATE) {
    return floatTo16BitPCM(float32Input);
  }
  const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
  const newLength = Math.round(float32Input.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetInput = 0;
  while (offsetResult < newLength) {
    const nextOffsetInput = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetInput; i < nextOffsetInput && i < float32Input.length; i++) {
      accum += float32Input[i];
      count++;
    }
    result[offsetResult] = count ? accum / count : 0;
    offsetResult++;
    offsetInput = nextOffsetInput;
  }
  return floatTo16BitPCM(result);
}

function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out.buffer;
}

function attachProcessing(stream, ws) {
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioContextCtor();
  const source = ctx.createMediaStreamSource(stream);
  // ScriptProcessorNode is deprecated but universally supported and simple
  // enough for Phase 2; an AudioWorklet swap is a drop-in later upgrade.
  const bufferSize = 4096;
  const processor = ctx.createScriptProcessor(bufferSize, 1, 1);

  processor.onaudioprocess = (event) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    const input = event.inputBuffer.getChannelData(0);
    const pcm = downsampleTo16kPcm(input, ctx.sampleRate);
    ws.send(pcm);
  };

  source.connect(processor);
  processor.connect(ctx.destination);

  _audioContext = ctx;
  _sourceNode = source;
  _processorNode = processor;
}

function teardownProcessing() {
  if (_processorNode) {
    try { _processorNode.disconnect(); } catch (_) { /* ignore */ }
    _processorNode.onaudioprocess = null;
    _processorNode = null;
  }
  if (_sourceNode) {
    try { _sourceNode.disconnect(); } catch (_) { /* ignore */ }
    _sourceNode = null;
  }
  if (_audioContext) {
    _audioContext.close().catch(() => {});
    _audioContext = null;
  }
}

/**
 * Start a streaming STT turn on the given (already-acquired) MediaStream.
 * opts: { onPartial(text), onFinal(text), onError(err) }
 */
export function startStream(stream, opts = {}) {
  _callbacks = opts || {};
  _stream = stream;

  return new Promise((resolve, reject) => {
    try {
      const ws = new WebSocket(wsUrl());
      ws.binaryType = 'arraybuffer';
      _ws = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'start', sampleRate: TARGET_SAMPLE_RATE }));
        attachProcessing(stream, ws);
        voiceTelemetry.emit('stt.stream.start');
        resolve();
      };

      ws.onmessage = (event) => {
        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch (_) {
          return;
        }
        if (payload.type === 'partial') {
          voiceTelemetry.emit('stt.partial', { chars: (payload.text || '').length });
          if (_callbacks.onPartial) _callbacks.onPartial(payload.text || '');
        } else if (payload.type === 'final') {
          voiceTelemetry.emit('stt.stream.final', { chars: (payload.text || '').length });
          if (_resolveStop) {
            _resolveStop(payload.text || '');
            _resolveStop = null;
          }
          if (_callbacks.onFinal) _callbacks.onFinal(payload.text || '');
          teardownProcessing();
        } else if (payload.type === 'error') {
          if (_callbacks.onError) _callbacks.onError(new Error(payload.message || 'Streaming STT error'));
          teardownProcessing();
        }
      };

      ws.onerror = () => {
        const err = new Error('Streaming STT connection error');
        if (_callbacks.onError) _callbacks.onError(err);
        reject(err);
      };

      ws.onclose = () => {
        teardownProcessing();
        if (_resolveStop) {
          _resolveStop('');
          _resolveStop = null;
        }
        _ws = null;
      };
    } catch (e) {
      reject(e);
    }
  });
}

/**
 * Signal end-of-turn and resolve with the final transcript text.
 */
export function stopStream() {
  return new Promise((resolve) => {
    if (!_ws || _ws.readyState !== WebSocket.OPEN) {
      teardownProcessing();
      resolve('');
      return;
    }
    _resolveStop = resolve;
    try {
      _ws.send(JSON.stringify({ type: 'stop' }));
    } catch (_) {
      teardownProcessing();
      resolve('');
    }
  });
}

/**
 * Discard the in-progress stream — no final text, no delivery.
 */
export function cancelStream() {
  teardownProcessing();
  if (_ws) {
    try {
      if (_ws.readyState === WebSocket.OPEN) {
        _ws.send(JSON.stringify({ type: 'cancel' }));
      }
      _ws.close();
    } catch (_) {
      /* ignore */
    }
    _ws = null;
  }
  _resolveStop = null;
}

const sttStreamModule = {
  isStreamingSttAvailable,
  setCachedProvider,
  startStream,
  stopStream,
  cancelStream,
};

export default sttStreamModule;

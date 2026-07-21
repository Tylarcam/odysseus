// static/js/audioOutput.js — route TTS playback to a chosen speaker/headphone

const STORAGE_ID = 'odysseus_audio_sink_id';
const STORAGE_LABEL = 'odysseus_audio_sink_label';
/** Stale Bluetooth/device IDs can leave setSinkId pending forever in Chromium. */
const SINK_TIMEOUT_MS = 1500;

let preferredSinkId = '';
let preferredSinkLabel = 'System default';

function withTimeout(promise, ms, label = 'timeout') {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(label)), ms);
    Promise.resolve(promise).then(
      (value) => { clearTimeout(timer); resolve(value); },
      (err) => { clearTimeout(timer); reject(err); },
    );
  });
}

function loadPreferred() {
  try {
    preferredSinkId = localStorage.getItem(STORAGE_ID) || '';
    preferredSinkLabel = localStorage.getItem(STORAGE_LABEL) || 'System default';
  } catch (_) {
    preferredSinkId = '';
    preferredSinkLabel = 'System default';
  }
}

loadPreferred();

export function supportsMediaSinkId() {
  return typeof HTMLMediaElement !== 'undefined'
    && typeof HTMLMediaElement.prototype.setSinkId === 'function';
}

export function supportsAudioContextSinkId() {
  return typeof AudioContext !== 'undefined'
    && typeof AudioContext.prototype.setSinkId === 'function';
}

export function supportsSelectAudioOutput() {
  return !!(navigator.mediaDevices && typeof navigator.mediaDevices.selectAudioOutput === 'function');
}

export function supportsAnyOutputSelection() {
  return supportsSelectAudioOutput() || supportsMediaSinkId();
}

export function getPreferredSink() {
  return { deviceId: preferredSinkId, label: preferredSinkLabel };
}

export function setPreferredSink(deviceId, label) {
  preferredSinkId = deviceId || '';
  preferredSinkLabel = label || (deviceId ? 'Speaker' : 'System default');
  try {
    localStorage.setItem(STORAGE_ID, preferredSinkId);
    localStorage.setItem(STORAGE_LABEL, preferredSinkLabel);
  } catch (_) { /* ignore */ }
  window.dispatchEvent(new CustomEvent('odysseus:audio-output-changed', {
    detail: getPreferredSink(),
  }));
}

export async function applySinkToMediaElement(audio) {
  if (!audio || !supportsMediaSinkId()) return;
  // System default: skip the API call — setSinkId('') can still hang on some builds.
  if (!preferredSinkId) return;
  try {
    await withTimeout(audio.setSinkId(preferredSinkId), SINK_TIMEOUT_MS, 'setSinkId timeout');
  } catch (err) {
    console.warn('Audio output: setSinkId on media element failed', err);
    // Drop the dead device preference so the next play uses the system default.
    setPreferredSink('', 'System default');
  }
}

export async function applySinkToAudioContext(ctx) {
  if (!ctx || !supportsAudioContextSinkId()) return;
  if (!preferredSinkId) return;
  try {
    await withTimeout(ctx.setSinkId(preferredSinkId), SINK_TIMEOUT_MS, 'AudioContext setSinkId timeout');
  } catch (err) {
    console.warn('Audio output: setSinkId on AudioContext failed', err);
    setPreferredSink('', 'System default');
  }
}

export async function enumerateOutputDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === 'audiooutput');
}

export async function refreshOutputDeviceOptions(selectEl) {
  if (!selectEl) return;
  const current = preferredSinkId;
  const devices = await enumerateOutputDevices();
  const labeled = devices.filter((d) => d.label);

  selectEl.innerHTML = '';
  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = 'System default';
  selectEl.appendChild(defaultOpt);

  labeled.forEach((d) => {
    const opt = document.createElement('option');
    opt.value = d.deviceId;
    opt.textContent = d.label;
    selectEl.appendChild(opt);
  });

  if (current && !labeled.some((d) => d.deviceId === current)) {
    const saved = document.createElement('option');
    saved.value = current;
    saved.textContent = preferredSinkLabel || 'Saved device';
    selectEl.appendChild(saved);
  }

  selectEl.value = current;
}

export async function pickOutputDevice() {
  if (!supportsSelectAudioOutput()) {
    throw new Error('Browser picker not available');
  }
  const device = await navigator.mediaDevices.selectAudioOutput();
  setPreferredSink(device.deviceId, device.label || 'Speaker');
  return device;
}

export function outputSelectionHint() {
  if (supportsSelectAudioOutput()) {
    return 'Choose where TTS plays — Bluetooth, iPhone, speakers, etc.';
  }
  if (supportsMediaSinkId()) {
    return 'Pick an output device from the list. Labels appear after you allow audio access.';
  }
  if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    return 'On iPhone, switch output in Control Center → AirPlay / speaker icon.';
  }
  return 'Your browser does not expose output selection. Use the system sound menu instead.';
}

const audioOutputModule = {
  supportsMediaSinkId,
  supportsAudioContextSinkId,
  supportsSelectAudioOutput,
  supportsAnyOutputSelection,
  getPreferredSink,
  setPreferredSink,
  applySinkToMediaElement,
  applySinkToAudioContext,
  enumerateOutputDevices,
  refreshOutputDeviceOptions,
  pickOutputDevice,
  outputSelectionHint,
};

export default audioOutputModule;

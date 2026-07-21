// static/js/voiceVisualizer.js
// Responsive voice visualizer — idle, listening (mic), speaking (TTS playback).
import { applySinkToAudioContext } from './audioOutput.js';

const BAR_COUNT = 28;
const IDLE_SPEED = 0.035;
const SIM_SPEED = 0.12;

let canvas = null;
let ctx = null;
let container = null;
let rafId = null;
let phase = 0;

let listening = false;
let speaking = false;
let thinking = false;
let listenStream = null;
let speakAudio = null;
let speakSimulated = false;

let audioCtx = null;
let analyser = null;
let analyserData = null;
let sourceNode = null;
let sourceKind = null; // 'stream' | 'audio'

let idleColor = 'rgba(140, 140, 150, 0.42)';
let listenColor = '#ff3b30';
let speakColor = '#7c9cff';
let thinkColor = '#f5a623';

function ensureAudioContext() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    audioCtx = new Ctx();
    applySinkToAudioContext(audioCtx).catch(() => {});
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function disconnectSource() {
  if (sourceNode) {
    try { sourceNode.disconnect(); } catch (_) { /* ignore */ }
    sourceNode = null;
  }
  sourceKind = null;
  analyser = null;
  analyserData = null;
}

function connectStream(stream) {
  const ac = ensureAudioContext();
  if (!ac || !stream) return;
  disconnectSource();
  analyser = ac.createAnalyser();
  analyser.fftSize = 64;
  analyser.smoothingTimeConstant = 0.75;
  analyserData = new Uint8Array(analyser.frequencyBinCount);
  sourceNode = ac.createMediaStreamSource(stream);
  sourceNode.connect(analyser);
  sourceKind = 'stream';
}

function connectAudioElement(audio) {
  const ac = ensureAudioContext();
  if (!ac || !audio) return;
  disconnectSource();
  try {
    analyser = ac.createAnalyser();
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.75;
    analyserData = new Uint8Array(analyser.frequencyBinCount);
    sourceNode = ac.createMediaElementSource(audio);
    sourceNode.connect(analyser);
    analyser.connect(ac.destination);
    sourceKind = 'audio';
  } catch (err) {
    console.warn('Voice visualizer: could not attach to audio element', err);
    speakSimulated = true;
  }
}

function applyVisualState() {
  if (!container) return;
  const active = listening || speaking || thinking;
  // Phase 3: listening overrides speaking during barge-in
  container.classList.toggle('is-listening', listening && !thinking);
  container.classList.toggle('is-speaking', speaking && !listening);
  container.classList.toggle('is-thinking', thinking && !speaking && !listening);
  container.classList.toggle('is-active', active);
  container.setAttribute('aria-hidden', active ? 'false' : 'true');
}

function reconcileAudioGraph() {
  disconnectSource();
  speakSimulated = false;

  if (listening) {
    if (listenStream) connectStream(listenStream);
    return;
  }

  if (speaking) {
    if (speakAudio) {
      connectAudioElement(speakAudio);
    } else {
      speakSimulated = true;
    }
    return;
  }
}

function setThinking(active) {
  thinking = !!active;
  if (active) {
    listening = false;
    speakSimulated = false;
  }
  reconcileAudioGraph();
  applyVisualState();
}

function setListening(active, stream) {
  listening = !!active;
  if (active) thinking = false;
  if (active && stream) listenStream = stream;
  if (!active) listenStream = null;
  reconcileAudioGraph();
  applyVisualState();
}

function setSpeaking(active, audio) {
  speaking = !!active;
  if (active) thinking = false;
  speakAudio = active ? (audio || null) : null;
  if (!active) speakSimulated = false;
  reconcileAudioGraph();
  applyVisualState();
}

function barHeight(index, total) {
  if (analyser && analyserData) {
    const bucket = Math.floor((index / total) * analyserData.length);
    return analyserData[bucket] / 255;
  }

  if (speaking && speakSimulated) {
    const wobble = Math.sin(phase * 2.4 + index * 0.55) * 0.22;
    const pulse = 0.45 + Math.sin(phase * 1.6 + index * 0.35) * 0.28;
    return Math.max(0.12, Math.min(1, pulse + wobble));
  }

  if (listening) {
    return 0.18 + Math.sin(phase * 2 + index * 0.4) * 0.08;
  }

  if (thinking) {
    const pulse = 0.35 + Math.sin(phase * 1.8 + index * 0.32) * 0.2;
    return Math.max(0.14, Math.min(0.75, pulse));
  }

  // Idle — gentle breathing wave
  return 0.14 + Math.sin(phase + index * 0.28) * 0.07;
}

function resizeCanvas() {
  if (!canvas || !container) return;
  const rect = container.getBoundingClientRect();
  const w = Math.max(1, Math.floor(rect.width));
  const h = Math.max(1, Math.floor(rect.height));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawFrame() {
  if (!ctx || !canvas || !container) return;

  if (analyser && analyserData) {
    analyser.getByteFrequencyData(analyserData);
  }

  if (container.classList.contains('is-speaking')) {
    ctx.fillStyle = speakColor;
  } else if (container.classList.contains('is-thinking')) {
    ctx.fillStyle = thinkColor;
  } else if (container.classList.contains('is-listening')) {
    ctx.fillStyle = listenColor;
  } else {
    ctx.fillStyle = idleColor;
  }

  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  ctx.clearRect(0, 0, w, h);

  const gap = 3;
  const barW = Math.max(2, (w - gap * (BAR_COUNT - 1)) / BAR_COUNT);
  const maxBarH = h * 0.88;
  const minBarH = h * 0.12;

  for (let i = 0; i < BAR_COUNT; i++) {
    const level = barHeight(i, BAR_COUNT);
    const barH = minBarH + (maxBarH - minBarH) * level;
    const x = i * (barW + gap);
    const y = (h - barH) / 2;
    const radius = Math.min(barW / 2, 3);
    if (typeof ctx.roundRect === 'function') {
      ctx.beginPath();
      ctx.roundRect(x, y, barW, barH, radius);
      ctx.fill();
    } else {
      ctx.fillRect(x, y, barW, barH);
    }
  }

  phase += listening || speaking || thinking ? SIM_SPEED : IDLE_SPEED;
  rafId = requestAnimationFrame(drawFrame);
}

function onListeningEvent(e) {
  const { active, stream } = e.detail || {};
  setListening(!!active, stream || null);
}

function onSpeakingEvent(e) {
  const { active, audio } = e.detail || {};
  setSpeaking(!!active, audio || null);
}

export function initVoiceVisualizer() {
  container = document.getElementById('voice-visualizer');
  if (!container) return;

  canvas = container.querySelector('canvas');
  if (!canvas) return;
  ctx = canvas.getContext('2d');

  const style = getComputedStyle(document.documentElement);
  idleColor = style.getPropertyValue('--voice-viz-idle').trim() || idleColor;
  listenColor = style.getPropertyValue('--voice-viz-listen').trim() || listenColor;
  speakColor = style.getPropertyValue('--voice-viz-speak').trim() || speakColor;
  thinkColor = style.getPropertyValue('--voice-viz-think').trim() || thinkColor;

  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
  window.addEventListener('odysseus:voice-listening', onListeningEvent);
  window.addEventListener('odysseus:voice-speaking', onSpeakingEvent);
  window.addEventListener('odysseus:voice-thinking', onThinkingEvent);
  window.addEventListener('odysseus:audio-output-changed', () => {
    if (audioCtx) applySinkToAudioContext(audioCtx).catch(() => {});
  });

  if (!rafId) rafId = requestAnimationFrame(drawFrame);
}

function onThinkingEvent(e) {
  const { active } = e.detail || {};
  setThinking(!!active);
}

export function emitVoiceListening(active, stream) {
  window.dispatchEvent(new CustomEvent('odysseus:voice-listening', {
    detail: { active: !!active, stream: stream || null },
  }));
}

export function emitVoiceSpeaking(active, audio) {
  window.dispatchEvent(new CustomEvent('odysseus:voice-speaking', {
    detail: { active: !!active, audio: audio || null },
  }));
}

export function emitVoiceThinking(active) {
  window.dispatchEvent(new CustomEvent('odysseus:voice-thinking', {
    detail: { active: !!active },
  }));
}

const voiceVisualizerModule = {
  initVoiceVisualizer,
  emitVoiceListening,
  emitVoiceSpeaking,
  emitVoiceThinking,
};

export default voiceVisualizerModule;

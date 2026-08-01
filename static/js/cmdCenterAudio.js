/**
 * V.A.U.L.T. HQ audio — BRIEF ME TTS rundown + earcons.
 * Concept match: vault-hq-v2 (Web Speech + short WebAudio oscillators).
 */

/** @typedef {'speaking'|'standby'} CmdAudioState */
/** @typedef {{ type: 'overdue'|'domain'|'all', domain?: string }} BriefHighlight */
/** @typedef {{ text: string, highlight?: BriefHighlight }} BriefLine */

let _onHighlight = null;
let _onClearHighlight = null;
let _onNowText = null;
let _onState = null;

let _voiceOn = true;
let _briefing = false;
let _briefToken = 0;
let _audioCtx = null;

function _ac() {
  if (!_audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    _audioCtx = new Ctx();
  }
  return _audioCtx;
}

function _setState(state) {
  try {
    _onState?.(state);
  } catch (_) {
    /* ignore callback errors */
  }
}

function _setNow(text) {
  try {
    _onNowText?.(text || '');
  } catch (_) {
    /* ignore */
  }
}

function _emitHighlight(hl) {
  if (!hl) return;
  try {
    _onHighlight?.(hl);
  } catch (_) {
    /* ignore */
  }
}

function _emitClear() {
  try {
    _onClearHighlight?.();
  } catch (_) {
    /* ignore */
  }
}

/**
 * Short oscillator burst. freqs play sequentially with `gap` between starts.
 * @param {number[]} freqs
 * @param {number} [dur]
 * @param {number} [gap]
 * @param {OscillatorType} [type]
 * @param {number} [vol]
 */
function chime(freqs, dur = 0.22, gap = 0.09, type = 'sine', vol = 0.12) {
  try {
    const ctx = _ac();
    if (!ctx) return;
    if (ctx.state === 'suspended') ctx.resume?.();
    let t = ctx.currentTime + 0.02;
    for (const f of freqs) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = type;
      o.frequency.value = f;
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g);
      g.connect(ctx.destination);
      o.start(t);
      o.stop(t + dur + 0.02);
      t += gap;
    }
  } catch (_) {
    /* WebAudio unavailable */
  }
}

/** Completion: rising high chime pair (vault-hq-v2). */
export function earconDone() {
  chime([880, 1174.7], 0.25, 0.12);
}

/** Attention: low triangle double-tap. */
export function earconAttn() {
  chime([220, 220], 0.3, 0.22, 'triangle', 0.1);
}

/** Message: soft single high ping. */
export function earconMsg() {
  chime([1318.5], 0.15, 0, 'sine', 0.08);
}

/** Error: descending dissonant saw. */
export function earconError() {
  chime([466.16, 415.3, 311.13], 0.18, 0.07, 'sawtooth', 0.1);
}

/**
 * @param {{
 *   onHighlight?: (hl: BriefHighlight) => void,
 *   onClearHighlight?: () => void,
 *   onNowText?: (text: string) => void,
 *   onState?: (state: CmdAudioState) => void,
 * }} [opts]
 */
export function initCmdCenterAudio({
  onHighlight,
  onClearHighlight,
  onNowText,
  onState,
} = {}) {
  _onHighlight = typeof onHighlight === 'function' ? onHighlight : null;
  _onClearHighlight = typeof onClearHighlight === 'function' ? onClearHighlight : null;
  _onNowText = typeof onNowText === 'function' ? onNowText : null;
  _onState = typeof onState === 'function' ? onState : null;
  _setState('standby');
}

export function destroyCmdCenterAudio() {
  stopBrief();
  _onHighlight = null;
  _onClearHighlight = null;
  _onNowText = null;
  _onState = null;
  if (_audioCtx) {
    try {
      _audioCtx.close?.();
    } catch (_) {
      /* ignore */
    }
    _audioCtx = null;
  }
}

export function setVoiceEnabled(on) {
  _voiceOn = !!on;
  if (!_voiceOn && typeof window !== 'undefined' && window.speechSynthesis) {
    try {
      window.speechSynthesis.cancel();
    } catch (_) {
      /* ignore */
    }
  }
}

export function stopBrief() {
  _briefing = false;
  _briefToken += 1;
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    try {
      window.speechSynthesis.cancel();
    } catch (_) {
      /* ignore */
    }
  }
  _emitClear();
  _setState('standby');
}

/**
 * Speak one line; falls back to timed simulation when muted or Speech API missing.
 * @param {string} text
 * @param {number} token
 * @returns {Promise<void>}
 */
function _speakLine(text, token) {
  return new Promise((resolve) => {
    const done = () => {
      if (token !== _briefToken) {
        resolve();
        return;
      }
      resolve();
    };

    const useSpeech =
      _voiceOn &&
      typeof window !== 'undefined' &&
      window.speechSynthesis &&
      typeof SpeechSynthesisUtterance !== 'undefined';

    if (!useSpeech) {
      const ms = Math.max(1800, String(text || '').length * 55);
      setTimeout(done, ms);
      return;
    }

    try {
      const u = new SpeechSynthesisUtterance(String(text || ''));
      u.rate = 1.03;
      u.pitch = 0.95;
      u.onend = done;
      u.onerror = done;
      window.speechSynthesis.speak(u);
    } catch (_) {
      const ms = Math.max(1800, String(text || '').length * 55);
      setTimeout(done, ms);
    }
  });
}

/**
 * Run BRIEF ME script sequentially.
 * @param {{ script?: BriefLine[] }} [opts]
 * @returns {Promise<void>}
 */
export async function runBrief({ script } = {}) {
  const lines = Array.isArray(script) ? script.filter((l) => l && String(l.text || '').trim()) : [];
  if (!lines.length) {
    _setNow('No brief script available.');
    _setState('standby');
    return;
  }

  stopBrief();
  _briefing = true;
  const token = _briefToken;
  earconMsg();
  _setState('speaking');

  for (let i = 0; i < lines.length; i++) {
    if (!_briefing || token !== _briefToken) break;
    const line = lines[i];
    const text = String(line.text || '').trim();
    _setNow(text);
    if (line.highlight) _emitHighlight(line.highlight);
    await _speakLine(text, token);
    if (!_briefing || token !== _briefToken) break;
    await new Promise((r) => setTimeout(r, 280));
  }

  // stopBrief() bumps _briefToken — skip completion side-effects when cancelled.
  if (token === _briefToken) {
    _briefing = false;
    _emitClear();
    _setState('standby');
    earconDone();
  }
}

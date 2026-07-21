// static/js/ttsControls.js — compact TTS controls popover (chat toolbar)
import {
  applySinkToMediaElement,
  getPreferredSink,
  outputSelectionHint,
  pickOutputDevice,
  refreshOutputDeviceOptions,
  setPreferredSink,
  supportsAnyOutputSelection,
  supportsSelectAudioOutput,
} from './audioOutput.js';

const OPENAI_VOICES = ['alloy', 'ash', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer'];
const SPEED_OPTIONS = ['0.5', '0.75', '1', '1.25', '1.5', '2'];
const TEST_TEXT = 'Hello, this is a test of text to speech.';

let popover = null;
let anchorBtn = null;
let previewAudio = null;
let previewPlaying = false;
let saveTimer = null;

function $(id) { return document.getElementById(id); }

function closePopover() {
  if (!popover) return;
  popover.classList.add('hidden');
}

function isOpen() {
  return popover && !popover.classList.contains('hidden');
}

function positionPopover() {
  if (!popover || !anchorBtn) return;
  const rect = anchorBtn.getBoundingClientRect();
  popover.style.left = `${Math.max(8, rect.left)}px`;
  popover.style.bottom = `${window.innerHeight - rect.top + 8}px`;
}

function syncVoiceChatUi(on) {
  const sendBtn = document.querySelector('.send-btn');
  if (sendBtn) sendBtn.classList.toggle('voice-chat-mode', !!on);
  const voiceChk = $('tts-ctrl-voice-chat');
  if (voiceChk) voiceChk.checked = !!on;
  if (window._updateSendBtnIcon) window._updateSendBtnIcon();
}

function persistVoiceChat(on) {
  try {
    const raw = localStorage.getItem('odysseus_toggle_state');
    const state = raw ? JSON.parse(raw) : {};
    state.voiceChatMode = !!on;
    localStorage.setItem('odysseus_toggle_state', JSON.stringify(state));
  } catch (_) { /* ignore */ }
}

function syncAutoplayUi(on) {
  const overflowTts = $('overflow-tts-btn');
  const autoplayChk = $('tts-ctrl-autoplay');
  if (autoplayChk) autoplayChk.checked = !!on;
  if (overflowTts) overflowTts.classList.toggle('active', !!on);
  if (window.aiTTSManager) window.aiTTSManager.autoPlay = !!on;
}

function persistAutoplay(on) {
  try {
    const raw = localStorage.getItem('odysseus_toggle_state');
    const state = raw ? JSON.parse(raw) : {};
    state.ttsMode = !!on;
    localStorage.setItem('odysseus_toggle_state', JSON.stringify(state));
  } catch (_) { /* ignore */ }
}

function isEndpointProvider(val) {
  return String(val || '').startsWith('endpoint:');
}

function updateVoiceField(provider, voiceVal) {
  const voiceSel = $('tts-ctrl-voice');
  const voiceInp = $('tts-ctrl-voice-text');
  if (!voiceSel || !voiceInp) return;

  voiceSel.innerHTML = '';
  voiceInp.style.display = 'none';
  voiceSel.style.display = '';

  if (provider === 'disabled') {
    voiceSel.style.display = 'none';
    return;
  }

  if (provider === 'browser') {
    voiceSel.style.display = 'none';
    voiceInp.style.display = '';
    voiceInp.value = voiceVal || '';
    voiceInp.placeholder = 'OS default voice (optional)';
    return;
  }

  if (isEndpointProvider(provider)) {
    OPENAI_VOICES.forEach((v) => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v.charAt(0).toUpperCase() + v.slice(1);
      voiceSel.appendChild(opt);
    });
    voiceSel.value = voiceVal || 'alloy';
    return;
  }

  // local Kokoro / Voice.ai — free text voice id
  voiceSel.style.display = 'none';
  voiceInp.style.display = '';
  if (provider === 'voiceai') {
    voiceInp.value = voiceVal || '';
    voiceInp.placeholder = 'voice UUID (optional)';
  } else {
    voiceInp.value = voiceVal || 'af_heart';
    voiceInp.placeholder = 'af_heart';
  }
}

function getVoiceValue(provider) {
  const voiceSel = $('tts-ctrl-voice');
  const voiceInp = $('tts-ctrl-voice-text');
  if (provider === 'browser' || provider === 'local' || provider === 'voiceai') {
    return (voiceInp?.value || '').trim();
  }
  if (isEndpointProvider(provider)) return voiceSel?.value || 'alloy';
  return '';
}

async function loadEndpoints(provSel) {
  const ttsKeywords = ['tts', 'audio'];
  try {
    const res = await fetch('/api/model-endpoints', { credentials: 'same-origin' });
    const endpoints = await res.json();
    endpoints.forEach((ep) => {
      if (!ep.is_enabled) return;
      const hasTts = (ep.models || []).some((m) => ttsKeywords.some((kw) => m.toLowerCase().includes(kw)));
      if (!hasTts) return;
      const opt = document.createElement('option');
      opt.value = `endpoint:${ep.id}`;
      opt.textContent = `${ep.name} (API)`;
      provSel.appendChild(opt);
    });
  } catch (e) {
    console.warn('TTS controls: failed to load endpoints', e);
  }
}

async function refreshToolbarVisibility() {
  const btn = $('tts-controls-btn');
  const overflowSpeech = $('overflow-tts-controls-btn');
  let show = false;
  try {
    const [settingsRes, statsRes] = await Promise.all([
      fetch('/api/auth/settings', { credentials: 'same-origin' }),
      fetch('/api/tts/stats', { credentials: 'same-origin' }),
    ]);
    const settings = await settingsRes.json();
    const stats = await statsRes.json();
    const off = settings.tts_enabled === false || !settings.tts_provider || settings.tts_provider === 'disabled';
    const ready = stats.available && stats.ready && stats.provider !== 'disabled';
    show = !off && ready;
    if (btn) {
      btn.style.display = show ? '' : 'none';
      btn.classList.toggle('active', !!(window.aiTTSManager && window.aiTTSManager.autoPlay));
    }
  } catch (_) {
    if (btn) btn.style.display = 'none';
  }
  if (overflowSpeech) overflowSpeech.style.display = show ? '' : 'none';
}

async function syncOutputUi() {
  const row = $('tts-ctrl-output-row');
  const select = $('tts-ctrl-output');
  const browseBtn = $('tts-ctrl-output-browse');
  const hint = $('tts-ctrl-output-hint');
  if (!row) return;

  const supported = supportsAnyOutputSelection();
  row.style.display = '';
  if (hint) {
    let text = outputSelectionHint();
    const prov = $('tts-ctrl-provider')?.value;
    if (prov === 'browser') {
      text += ' Browser voice output follows the system default — use Output for server/local TTS.';
    }
    hint.textContent = text;
  }
  if (select) select.style.display = supported ? '' : 'none';
  if (browseBtn) browseBtn.style.display = supported ? '' : 'none';
  if (!supported) return;

  const { label } = getPreferredSink();
  if (browseBtn) browseBtn.title = label;

  if (select) await refreshOutputDeviceOptions(select);

  if (window.voiceRealtimeModule?.isConnected?.()) {
    window.dispatchEvent(new CustomEvent('odysseus:audio-output-changed', {
      detail: getPreferredSink(),
    }));
  }
}

function wireOutputControls() {
  const select = $('tts-ctrl-output');
  const browseBtn = $('tts-ctrl-output-browse');

  browseBtn?.addEventListener('click', async (e) => {
    e.stopPropagation();
    const msg = $('tts-ctrl-msg');
    try {
      if (supportsSelectAudioOutput()) {
        await pickOutputDevice();
        await syncOutputUi();
        if (msg) msg.textContent = `Output: ${getPreferredSink().label}`;
      } else if (select) {
        select.focus();
        if (msg) msg.textContent = 'Choose a device from the list';
      }
    } catch (err) {
      if (err?.name === 'NotAllowedError') return;
      if (msg) msg.textContent = err.message || 'Could not pick output';
    }
  });

  select?.addEventListener('change', () => {
    const opt = select.selectedOptions[0];
    setPreferredSink(select.value, opt?.textContent || 'Speaker');
    const msg = $('tts-ctrl-msg');
    if (msg) msg.textContent = `Output: ${getPreferredSink().label}`;
  });

  if (navigator.mediaDevices?.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', () => {
      if (isOpen()) syncOutputUi().catch(() => {});
    });
  }
}

async function syncSttUi() {
  const sttEnabledChk = $('tts-ctrl-stt-enabled');
  const sttProvSel = $('tts-ctrl-stt-provider');
  const sttHint = $('tts-ctrl-stt-hint');
  const voiceChatHint = $('tts-ctrl-voice-chat-hint');
  const voiceChatChk = $('tts-ctrl-voice-chat');
  if (!sttEnabledChk || !sttProvSel) return;

  try {
    const res = await fetch('/api/auth/settings', { credentials: 'same-origin' });
    const settings = await res.json();
    sttEnabledChk.checked = settings.stt_enabled === true;
    if (settings.stt_provider && settings.stt_provider !== 'disabled') {
      sttProvSel.value = settings.stt_provider;
    } else if (!sttEnabledChk.checked) {
      sttProvSel.value = 'browser';
    }
  } catch (_) { /* ignore */ }

  if (window.voiceChatModule?.refreshRealtimeState) {
    await window.voiceChatModule.refreshRealtimeState();
  }
  if (window.voiceChatModule?.refreshSttState) {
    await window.voiceChatModule.refreshSttState();
  }
  const blockReason = window.voiceChatModule?.getSttBlockReason
    ? await window.voiceChatModule.getSttBlockReason()
    : null;
  const realtimeOn = window.voiceRealtimeModule?.isConnected?.();
  const featureOn = window.voiceChatModule?.isVoiceChatFeatureEnabled?.() !== false;

  const voiceRow = voiceChatChk?.closest('.tts-controls-toggle');
  if (voiceRow) voiceRow.style.display = featureOn ? '' : 'none';

  if (sttHint) {
    if (!featureOn) {
      sttHint.textContent = 'Voice chat is disabled in Settings.';
      sttHint.style.color = 'var(--red)';
    } else if (realtimeOn) {
      sttHint.textContent = 'Realtime voice active — speak naturally (uses a live AI session).';
      sttHint.style.color = '';
    } else if (blockReason) {
      sttHint.textContent = blockReason;
      sttHint.style.color = 'var(--red)';
    } else {
      sttHint.textContent = 'STT ready — voice falls back to push-to-talk when realtime is unavailable.';
      sttHint.style.color = '';
    }
  }
  if (voiceChatHint) {
    if (!featureOn) {
      voiceChatHint.textContent = 'Enable voice chat in Settings → AI to use realtime or push-to-talk.';
      voiceChatHint.style.display = '';
    } else {
      voiceChatHint.textContent = 'Voice uses a realtime AI session when available; otherwise push-to-talk with speech-to-text.';
      voiceChatHint.style.display = blockReason ? '' : 'none';
    }
  }
  if (voiceChatChk && blockReason) {
    voiceChatChk.disabled = false;
  }
}

async function saveSttSettings() {
  const sttEnabledChk = $('tts-ctrl-stt-enabled');
  const sttProvSel = $('tts-ctrl-stt-provider');
  const msg = $('tts-ctrl-msg');
  if (!sttEnabledChk || !sttProvSel) return;

  const enabled = sttEnabledChk.checked;
  let provider = sttProvSel.value;
  if (enabled && provider === 'disabled') provider = 'browser';

  try {
    await fetch('/api/auth/settings', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stt_enabled: enabled,
        stt_provider: provider,
        stt_model: 'base',
        stt_language: '',
      }),
    });
    if (window.voiceRecorderModule?.refreshSttProvider) {
      await window.voiceRecorderModule.refreshSttProvider();
    }
    await syncSttUi();
    if (msg) {
      msg.textContent = 'STT saved';
      setTimeout(() => { if (msg.textContent === 'STT saved') msg.textContent = ''; }, 1500);
    }
  } catch (e) {
    if (msg) msg.textContent = 'STT save failed';
  }
}

async function loadState() {
  const provSel = $('tts-ctrl-provider');
  const speedSel = $('tts-ctrl-speed');
  const enabledChk = $('tts-ctrl-enabled');
  if (!provSel || !speedSel) return;

  const res = await fetch('/api/auth/settings', { credentials: 'same-origin' });
  const settings = await res.json();

  if (enabledChk) enabledChk.checked = settings.tts_enabled !== false;
  if (settings.tts_provider) provSel.value = settings.tts_provider;
  if (settings.tts_speed) speedSel.value = settings.tts_speed;
  updateVoiceField(provSel.value, settings.tts_voice || '');

  try {
    const raw = localStorage.getItem('odysseus_toggle_state');
    const state = raw ? JSON.parse(raw) : {};
    syncAutoplayUi(!!state.ttsMode);
    syncVoiceChatUi(!!state.voiceChatMode);
  } catch (_) { /* ignore */ }

  await syncOutputUi();
  await syncSttUi();
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveSettings, 350);
}

async function saveSettings(clearCache) {
  const provSel = $('tts-ctrl-provider');
  const speedSel = $('tts-ctrl-speed');
  const enabledChk = $('tts-ctrl-enabled');
  const msg = $('tts-ctrl-msg');
  if (!provSel) return;

  const provider = provSel.value;
  const body = {
    tts_enabled: enabledChk ? enabledChk.checked : true,
    tts_provider: provider,
    tts_voice: getVoiceValue(provider) || (isEndpointProvider(provider) ? 'alloy' : 'af_heart'),
    tts_speed: speedSel?.value || '1',
    tts_model: 'tts-1',
  };

  try {
    await fetch('/api/auth/settings', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (clearCache) {
      fetch('/api/tts/clear-cache', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
    }
    if (window.aiTTSManager) await window.aiTTSManager.checkAvailability();
    await refreshToolbarVisibility();
    if (msg) {
      msg.textContent = 'Saved';
      setTimeout(() => { if (msg.textContent === 'Saved') msg.textContent = ''; }, 1500);
    }
  } catch (e) {
    if (msg) msg.textContent = 'Save failed';
  }
}

function resetPreviewBtn(btn) {
  previewPlaying = false;
  if (btn) btn.textContent = 'Preview';
}

async function runPreview() {
  const btn = $('tts-ctrl-preview');
  const provSel = $('tts-ctrl-provider');
  const speedSel = $('tts-ctrl-speed');
  const msg = $('tts-ctrl-msg');
  if (!btn || !provSel) return;

  if (previewPlaying) {
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    window.speechSynthesis.cancel();
    if (window.aiTTSManager) window.aiTTSManager.stop();
    resetPreviewBtn(btn);
    return;
  }

  const provider = provSel.value;
  if (provider === 'disabled') {
    if (msg) msg.textContent = 'Enable a provider first';
    return;
  }

  previewPlaying = true;
  btn.textContent = 'Stop';

  try {
    await saveSettings(true);
    if (provider === 'browser') {
      if (!('speechSynthesis' in window)) throw new Error('Browser TTS not supported');
      const utt = new SpeechSynthesisUtterance(TEST_TEXT);
      const voiceVal = getVoiceValue(provider);
      if (voiceVal) {
        const voices = window.speechSynthesis.getVoices();
        const target = voiceVal.toLowerCase();
        const match = voices.find((v) => v.name.toLowerCase() === target)
          || voices.find((v) => v.name.toLowerCase().includes(target));
        if (match) utt.voice = match;
      }
      utt.rate = parseFloat(speedSel?.value) || 1;
      await new Promise((resolve, reject) => {
        utt.onend = resolve;
        utt.onerror = (e) => reject(new Error(e.error || 'browser TTS error'));
        window.speechSynthesis.speak(utt);
      });
    } else {
      const res = await fetch('/api/tts/synthesize', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: TEST_TEXT, format: 'audio' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || 'Synthesis failed');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      previewAudio = new Audio(url);
      await applySinkToMediaElement(previewAudio);
      await new Promise((resolve, reject) => {
        previewAudio.onended = () => { URL.revokeObjectURL(url); previewAudio = null; resolve(); };
        previewAudio.onerror = () => { URL.revokeObjectURL(url); previewAudio = null; reject(new Error('Playback failed')); };
        previewAudio.play().catch(reject);
      });
    }
  } catch (e) {
    if (msg) msg.textContent = e.message || 'Preview failed';
  } finally {
    resetPreviewBtn(btn);
  }
}

function wireControls() {
  popover = $('tts-controls-popover');
  anchorBtn = $('tts-controls-btn');
  if (!popover || !anchorBtn) return;

  const provSel = $('tts-ctrl-provider');
  const speedSel = $('tts-ctrl-speed');
  const enabledChk = $('tts-ctrl-enabled');
  const autoplayChk = $('tts-ctrl-autoplay');
  const voiceChatChk = $('tts-ctrl-voice-chat');
  const sttEnabledChk = $('tts-ctrl-stt-enabled');
  const sttProvSel = $('tts-ctrl-stt-provider');
  const voiceSel = $('tts-ctrl-voice');
  const voiceInp = $('tts-ctrl-voice-text');
  const settingsLink = $('tts-ctrl-open-settings');

  anchorBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (isOpen()) {
      closePopover();
      return;
    }
    openTtsControls(anchorBtn);
  });

  document.addEventListener('click', (e) => {
    if (!isOpen()) return;
    if (popover.contains(e.target) || anchorBtn.contains(e.target)) return;
    closePopover();
  });

  window.addEventListener('resize', () => { if (isOpen()) positionPopover(); });

  provSel?.addEventListener('change', () => {
    const prov = provSel.value;
    if (prov === 'local') updateVoiceField(prov, 'af_heart');
    else if (prov === 'browser') updateVoiceField(prov, '');
    else if (isEndpointProvider(prov)) updateVoiceField(prov, 'alloy');
    else updateVoiceField(prov, '');
    syncOutputUi().catch(() => {});
    scheduleSave();
  });

  speedSel?.addEventListener('change', () => saveSettings(true));
  voiceSel?.addEventListener('change', () => saveSettings(true));
  voiceInp?.addEventListener('change', () => saveSettings(false));
  enabledChk?.addEventListener('change', () => saveSettings(false));

  autoplayChk?.addEventListener('change', () => {
    const on = autoplayChk.checked;
    syncAutoplayUi(on);
    persistAutoplay(on);
  });

  voiceChatChk?.addEventListener('change', async () => {
    const on = voiceChatChk.checked;
    if (window.voiceChatModule?.setActive) {
      const ok = await window.voiceChatModule.setActive(on, {
        showError: (msg) => {
          const el = $('tts-ctrl-msg');
          if (el) el.textContent = msg || 'Voice chat unavailable';
        },
      });
      if (!ok) {
        voiceChatChk.checked = false;
        syncVoiceChatUi(false);
        return;
      }
    } else {
      syncVoiceChatUi(on);
      persistVoiceChat(on);
      if (on) syncAutoplayUi(true);
    }
  });

  sttEnabledChk?.addEventListener('change', () => {
    if (sttEnabledChk.checked && sttProvSel?.value === 'disabled') {
      sttProvSel.value = 'browser';
    }
    saveSttSettings().catch(() => {});
  });
  sttProvSel?.addEventListener('change', () => saveSttSettings().catch(() => {}));

  document.addEventListener('odysseus:stt-settings-changed', () => {
    syncSttUi().catch(() => {});
  });

  document.addEventListener('odysseus:stt-blocked', (e) => {
    const el = $('tts-ctrl-msg');
    if (el && e.detail?.message) el.textContent = e.detail.message;
    syncSttUi().catch(() => {});
  });

  document.addEventListener('odysseus:voice-chat-changed', (e) => {
    syncVoiceChatUi(!!e.detail?.active);
    persistVoiceChat(!!e.detail?.active);
  });

  $('tts-ctrl-preview')?.addEventListener('click', (e) => { e.stopPropagation(); runPreview(); });
  $('tts-ctrl-stop')?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (window.aiTTSManager) window.aiTTSManager.stop();
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    window.speechSynthesis.cancel();
    resetPreviewBtn($('tts-ctrl-preview'));
  });

  settingsLink?.addEventListener('click', (e) => {
    e.preventDefault();
    closePopover();
    if (window.settingsModule?.open) window.settingsModule.open('audio');
  });
}

export function openTtsControls(anchorEl) {
  if (!popover) popover = $('tts-controls-popover');
  if (anchorEl) anchorBtn = anchorEl;
  else if (!anchorBtn) anchorBtn = $('tts-controls-btn');
  if (!popover || !anchorBtn) return;
  positionPopover();
  popover.classList.remove('hidden');
  loadState().catch(() => {});
}

export async function initTtsControls() {
  const provSel = $('tts-ctrl-provider');
  if (provSel) await loadEndpoints(provSel);
  wireOutputControls();
  wireControls();
  await refreshToolbarVisibility();
  window.refreshTtsControls = refreshToolbarVisibility;
}

const ttsControlsModule = { initTtsControls, refreshToolbarVisibility, openTtsControls };
export default ttsControlsModule;

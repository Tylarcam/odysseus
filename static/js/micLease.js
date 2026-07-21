// static/js/micLease.js — shared mic lease with Clicky (via /api/voice/mic/*)

let _token = null;
let _mode = null;

const HOLDER = 'odysseus';

export async function getMicLeaseStatus() {
  try {
    const res = await fetch('/api/voice/mic/status', { credentials: 'same-origin' });
    if (!res.ok) return { available: true, holder: null };
    return res.json();
  } catch (_) {
    return { available: true, holder: null };
  }
}

export async function claimMicLease(mode = 'recorder', ttlSec = 90) {
  try {
    const res = await fetch('/api/voice/mic/claim', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ holder: HOLDER, mode, ttl_sec: ttlSec }),
    });
    const data = await res.json().catch(() => ({}));
    if (data.ok) {
      _token = data.token;
      _mode = mode;
    }
    return data;
  } catch (e) {
    return { ok: false, reason: 'network', message: e.message || String(e) };
  }
}

export async function releaseMicLease() {
  const token = _token;
  _token = null;
  _mode = null;
  if (!token) return { ok: true, released: false };
  try {
    const res = await fetch('/api/voice/mic/release', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ holder: HOLDER, token }),
    });
    return res.json().catch(() => ({ ok: true }));
  } catch (_) {
    return { ok: true };
  }
}

export function micBusyMessage(status) {
  if (!status || status.available !== false) return null;
  if (status.holder === 'clicky') {
    return 'Microphone in use by Clicky. Release Ctrl+Alt (or wait for Clicky to finish) and try again.';
  }
  return 'Microphone is in use by another voice session. Stop voice chat or wait a moment, then try again.';
}

export function hasMicLease() {
  return !!_token;
}

const micLeaseModule = {
  getMicLeaseStatus,
  claimMicLease,
  releaseMicLease,
  micBusyMessage,
  hasMicLease,
};

export default micLeaseModule;

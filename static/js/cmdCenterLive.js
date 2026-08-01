/**
 * V.A.U.L.T. HQ live poll + connection resilience (Phase 5).
 *
 * Parent owns fetch/apply (in-place refresh). This module only schedules
 * polls, backoff, Visibility API pause/resume, and connection-state signals.
 *
 * Wired into `cmdCenter.js` (`_startLiveUpdates` / `_pauseSceneAndClock`).
 * See `.tmp/hq-phases/p5/ASSEMBLY.md` for the original wire-up notes.
 */

/** @typedef {'live'|'stale'|'offline'|'stopped'} CmdCenterLiveState */
/** @typedef {'live'|'stale'|'offline'} CmdCenterConnectionState */

const DEFAULT_INTERVAL_MS = 30000;
const MAX_BACKOFF_MS = 120000;

/** @type {ReturnType<typeof setTimeout>|null} */
let _timer = null;
/** @type {CmdCenterLiveState} */
let _state = 'stopped';
let _started = false;
let _pollInFlight = false;
let _failStreak = 0;
let _currentIntervalMs = DEFAULT_INTERVAL_MS;
/** @type {string|null} ISO timestamp of last successful sync */
let _lastSyncedAt = null;
/** @type {((state: CmdCenterConnectionState) => void)|null} */
let _onConnectionChange = null;
/** @type {(() => Promise<unknown>)|null} */
let _fetchData = null;
/** @type {((data?: unknown) => void)|null} */
let _applyUpdate = null;
let _baseIntervalMs = DEFAULT_INTERVAL_MS;
let _visibilityBound = false;

function _esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _formatRelative(iso) {
  if (!iso) return '';
  try {
    const ms = Date.now() - new Date(iso).getTime();
    if (!Number.isFinite(ms) || ms < 0) return '';
    const secs = Math.floor(ms / 1000);
    if (secs < 45) return 'just now';
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return '';
  }
}

function _clearTimer() {
  if (_timer != null) {
    clearTimeout(_timer);
    _timer = null;
  }
}

/**
 * @param {CmdCenterLiveState} next
 */
function _setState(next) {
  if (_state === next) return;
  _state = next;
  if (next === 'stopped') return;
  try {
    _onConnectionChange?.(/** @type {CmdCenterConnectionState} */ (next));
  } catch (_) { /* parent UI must not break the poll loop */ }
}

function _nextBackoffMs() {
  // On failure: 30s → 60s → 120s max (doubling from base by fail streak).
  const steps = Math.min(Math.max(_failStreak - 1, 0), 2); // 0,1,2 → ×1,×2,×4
  return Math.min(_baseIntervalMs * (2 ** steps), MAX_BACKOFF_MS);
}

function _schedule(ms) {
  _clearTimer();
  if (!_started) return;
  if (typeof document !== 'undefined' && document.hidden) return;
  _timer = setTimeout(() => {
    _timer = null;
    void _tick();
  }, ms);
}

async function _tick() {
  if (!_started || _pollInFlight) return;
  if (typeof document !== 'undefined' && document.hidden) return;

  _pollInFlight = true;
  try {
    if (typeof _fetchData !== 'function') {
      throw new Error('cmdCenterLive: fetchData not provided');
    }
    const payload = await _fetchData();
    // Success: reset backoff, apply in-place update (no full white-flash paint).
    _failStreak = 0;
    _currentIntervalMs = _baseIntervalMs;
    _lastSyncedAt = new Date().toISOString();
    _setState('live');
    try {
      if (payload !== undefined && payload !== null) {
        _applyUpdate?.(payload);
      } else {
        _applyUpdate?.();
      }
    } catch (_) { /* apply errors are parent-side */ }
  } catch (_) {
    _failStreak += 1;
    _currentIntervalMs = _nextBackoffMs();
    // First failure with prior data → stale; repeated / no prior sync → offline
    if (_failStreak >= 2 || !_lastSyncedAt) {
      _setState('offline');
    } else {
      _setState('stale');
    }
  } finally {
    _pollInFlight = false;
    if (_started) _schedule(_currentIntervalMs);
  }
}

function _onVisibilityChange() {
  if (!_started) return;
  if (typeof document === 'undefined') return;
  if (document.hidden) {
    _clearTimer();
    return;
  }
  // Resume: immediate resync, then normal cadence.
  void _tick();
}

function _bindVisibility() {
  if (_visibilityBound || typeof document === 'undefined') return;
  document.addEventListener('visibilitychange', _onVisibilityChange);
  _visibilityBound = true;
}

function _unbindVisibility() {
  if (!_visibilityBound || typeof document === 'undefined') return;
  document.removeEventListener('visibilitychange', _onVisibilityChange);
  _visibilityBound = false;
}

/**
 * Start live polling. Safe to call again — restarts cleanly (no stacked timers).
 *
 * @param {object} [opts]
 * @param {() => Promise<unknown>} [opts.fetchData] async fetch; throw on failure.
 *   Return latest payload to pass into applyUpdate(data); return void if parent
 *   already mutated shared state (then applyUpdate() is called with no args).
 * @param {(data?: unknown) => void} [opts.applyUpdate] in-place refresh (no full remount)
 * @param {(state: CmdCenterConnectionState) => void} [opts.onConnectionChange]
 * @param {number} [opts.intervalMs=30000]
 */
export function startCmdCenterLive({
  fetchData,
  applyUpdate,
  onConnectionChange,
  intervalMs = DEFAULT_INTERVAL_MS,
} = {}) {
  stopCmdCenterLive();

  _fetchData = typeof fetchData === 'function' ? fetchData : null;
  _applyUpdate = typeof applyUpdate === 'function' ? applyUpdate : null;
  _onConnectionChange = typeof onConnectionChange === 'function' ? onConnectionChange : null;
  _baseIntervalMs = Math.max(1000, Number(intervalMs) || DEFAULT_INTERVAL_MS);
  _currentIntervalMs = _baseIntervalMs;
  _failStreak = 0;
  // Parent starts this after a successful open fetch — seed so first failure → stale.
  _lastSyncedAt = new Date().toISOString();
  _started = true;
  _state = 'live'; // optimistic until first tick; parent already synced on open
  _bindVisibility();

  // First scheduled poll after interval (parent just fetched on open).
  // If tab is hidden, wait until visible.
  if (typeof document !== 'undefined' && document.hidden) return;
  _schedule(_baseIntervalMs);
}

/** Stop polling and clear timers. Idempotent. */
export function stopCmdCenterLive() {
  _started = false;
  _pollInFlight = false;
  _clearTimer();
  _unbindVisibility();
  _fetchData = null;
  _applyUpdate = null;
  _onConnectionChange = null;
  _failStreak = 0;
  _currentIntervalMs = DEFAULT_INTERVAL_MS;
  _state = 'stopped';
}

/** @returns {CmdCenterLiveState} */
export function getCmdCenterLiveState() {
  return _state;
}

/** ISO timestamp of last successful live poll, or null. */
export function getCmdCenterLastSyncedAt() {
  return _lastSyncedAt;
}

/**
 * Banner markup for parent to inject (e.g. above `#cmd-sync-label` / error strip).
 * - live: empty (no banner / subtle — parent sync label is enough)
 * - stale: amber STALE line with last sync relative time
 * - offline: red OFFLINE reconnecting line
 *
 * @param {CmdCenterConnectionState|CmdCenterLiveState} state
 * @param {{ lastSyncedAt?: string|null }} [opts]
 * @returns {string} HTML string
 */
export function renderLiveBanner(state, { lastSyncedAt = _lastSyncedAt } = {}) {
  if (state === 'live' || state === 'stopped') return '';

  const rel = _formatRelative(lastSyncedAt) || 'unknown';
  if (state === 'stale') {
    return `<div class="cmd-live-banner cmd-live-banner--stale" role="status" data-live-state="stale">STALE — last sync ${_esc(rel)}</div>`;
  }
  if (state === 'offline') {
    return `<div class="cmd-live-banner cmd-live-banner--offline" role="alert" data-live-state="offline">OFFLINE — reconnecting…</div>`;
  }
  return '';
}

/**
 * Suggested CSS for banners (parent may inline into cmd-center styles).
 * Not injected automatically — assembly step owns styles.
 */
export const CMD_LIVE_BANNER_CSS = `
.cmd-live-banner {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 6px 12px;
  text-align: center;
}
.cmd-live-banner--stale {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
  border-bottom: 1px solid rgba(245, 158, 11, 0.28);
}
.cmd-live-banner--offline {
  background: rgba(239, 68, 68, 0.14);
  color: #f87171;
  border-bottom: 1px solid rgba(239, 68, 68, 0.3);
}
`;

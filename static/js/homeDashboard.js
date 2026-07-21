/**
 * Home dashboard — recent chats on the welcome screen ("Jump Back In").
 */

const API_BASE = window.location.origin;

let _container = null;
let _data = null;
let _loading = false;

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
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const diffMs = Date.now() - d.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 7) return `${days}d ago`;
    return d.toLocaleString([], { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

function _setRecentsLayout(hasRecents) {
  const cc = document.getElementById('chat-container');
  if (cc) cc.classList.toggle('welcome-has-recents', !!hasRecents);
}

async function _fetchDashboard() {
  _loading = true;
  try {
    const res = await fetch(`${API_BASE}/api/sessions/recent?limit=5`, {
      credentials: 'same-origin',
    });
    if (!res.ok) throw new Error(`Recent sessions fetch failed (${res.status})`);
    _data = await res.json();
  } catch (err) {
    console.warn('Recent sessions fetch failed', err);
    _data = { sessions: [], count: 0 };
  } finally {
    _loading = false;
  }
}

function _openSession(sessionId) {
  if (!sessionId) return;
  const sm = window.sessionModule;
  if (sm?.selectSession) {
    sm.selectSession(sessionId);
    return;
  }
  window.location.hash = sessionId;
}

function _render() {
  if (!_container) return;
  const sessions = _data?.sessions || [];

  if (_loading) {
    _setRecentsLayout(false);
    _container.hidden = false;
    _container.innerHTML = '<div class="home-dashboard-loading">Loading…</div>';
    return;
  }

  if (!sessions.length) {
    _setRecentsLayout(false);
    _container.hidden = true;
    _container.innerHTML = '';
    return;
  }

  _setRecentsLayout(true);

  const cards = sessions.map((session) => {
    const when = _formatRelative(session.last_message_at);
    const preview = (session.preview || '').trim() || 'No messages yet';
    const previewClass = session.preview ? 'home-dashboard-card-preview' : 'home-dashboard-card-preview is-empty';
    return `
      <button type="button" class="home-dashboard-chat-card" data-session-id="${_esc(session.id)}" title="${_esc(session.title || 'Untitled chat')}">
        <header class="home-dashboard-card-head">
          <span class="home-dashboard-card-name">${_esc(session.title || 'Untitled chat')}</span>
          <span class="home-dashboard-card-when">${when ? _esc(when) : ''}</span>
        </header>
        <p class="${previewClass}">${_esc(preview)}</p>
      </button>`;
  }).join('');

  _container.hidden = false;
  _container.innerHTML = `
    <div class="home-dashboard-head">
      <span class="home-dashboard-title">Jump Back In</span>
      <button type="button" class="home-dashboard-refresh" title="Refresh">↻</button>
    </div>
    <div class="home-dashboard-cards">${cards}</div>`;

  _container.querySelector('.home-dashboard-refresh')?.addEventListener('click', () => {
    refreshHomeDashboard();
  });

  _container.querySelectorAll('.home-dashboard-chat-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      _openSession(btn.dataset.sessionId);
    });
  });
}

function _welcomeVisible() {
  const ws = document.getElementById('welcome-screen');
  return !!(ws && !ws.classList.contains('hidden'));
}

export async function refreshHomeDashboard() {
  if (!_welcomeVisible()) {
    _setRecentsLayout(false);
    return;
  }
  if (!_container) _container = document.getElementById('home-dashboard');
  if (!_container) return;
  await _fetchDashboard();
  if (!_welcomeVisible()) return;
  _render();
}

export function initHomeDashboard() {
  _container = document.getElementById('home-dashboard');
  if (!_container) return;
  if (_welcomeVisible()) refreshHomeDashboard();
}

const homeDashboardModule = { initHomeDashboard, refreshHomeDashboard };
export default homeDashboardModule;

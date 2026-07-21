/**
 * V.A.U.L.T. — Odysseus Command Center (situation room HUD).
 */

import * as Modals from './modalManager.js';
import notesModule from './notes.js';
import agentBinModule from './agentBin.js';
import tasksModule from './tasks.js';
import calendarModule from './calendar.js';
import documentModule from './document.js';
import sessionModule from './sessions.js';
import {
  initCmdCenterScene,
  updateCmdCenterScene,
  pauseCmdCenterScene,
  resumeCmdCenterScene,
  disposeCmdCenterScene,
  setCardAnchors,
  isCmdCenterSceneAutoSpin,
  toggleCmdCenterSceneAutoSpin,
} from './cmdCenterScene.js';
import { openJobAttentionPanel } from './cmdCenterJobs.js';
import { wireSwipeDismiss, collapseSidebarForMobileSheet } from './panelSheet.js';
// DISABLED with /clicky: Docker cannot spawn Windows WPF via /api/clicky/start.
// import { launchClicky, clickyLaunchToast } from './clickyLaunch.js';

const API_BASE = window.location.origin;
const PANEL_ID = 'cmd-center-panel';
const PANE_ID = 'cmd-center-pane';

const DATA = {
  title: 'V.A.U.L.T.',
  subtitle: 'Odysseus Command Center',
  status: [],
  branch_health: [],
  vitals: [],
  priority_queue: [],
  directives: [],
  documents: [],
  stage_cards: [],
  hero: {
    label: 'Primary Directive — Live Deploy',
    title: 'Stand by',
    value: 0,
    unit: 'NOTES',
    velocity: 'Syncing…',
    explain: '',
    cta_label: 'Vault sync',
  },
  commands: [],
  suggested_commands: [],
  wire: [],
  jobs_detail: { ready_to_apply: [], needs_review: [] },
  audio: {
    tts: 'standby',
    label: 'TTS Standby',
    hint: 'Tap Audio or hold Space 3s · delegate in agent voice',
  },
};

let _open = false;
let _data = { ...DATA };
let _fetchError = null;
let _syncedAt = null;
let _clockTimer = null;
let _voiceUiHandler = null;
let _heroAnimated = false;
let _refreshTimer = null;
let _cardAnchorObserver = null;
let _mobileTab = 'hud';
let _resizeHandler = null;
let _visSettingsWired = false;
let _infoPopoverWired = false;

const SOFT_REFRESH_MS = 30000;
const VIS_STORAGE_KEY = 'odysseus-cmd-center-visibility';

/** Component atlas — keep in sync with docs/vault-cmd-center-component-atlas.md */
const CMD_COMPONENT_ATLAS = {
  status_pills: {
    label: 'Status Pills',
    goal: 'Instant branch health across Core, Mem, Prod, Intel, Comms, Agency, Relay, Voice, Mycelia.',
    provenance: 'branch_health / status from build_cmd_center → _build_branch_health().',
    action: 'Click a pill to open that branch surface (notes, tasks, agent bin, jobs, etc.).',
  },
  vitals: {
    label: 'System Vitals',
    goal: 'Capacity snapshot — notes, documents, scheduled tasks, agent-bin attention.',
    provenance: 'vitals[] — live counts from notes, docs, active tasks, handoff queue.',
    action: 'Click a row to open Notes, Library, Tasks, or Agent Bin.',
  },
  priority_queue: {
    label: 'Priority Queue',
    goal: 'Single ranked list of what needs you next.',
    provenance: 'priority_queue / directives — handoffs (100) → jobs → due/pinned notes → tasks.',
    action: 'Click a row to open the note, job panel, or handoff inbox.',
  },
  swarm_activity: {
    label: 'Swarm Activity',
    goal: 'See recent Mycelia agent runs without opening Tasks.',
    provenance: 'agent_activity[] — last task_runs, swarm tasks prioritized.',
    action: 'Click a row to open the scheduled task.',
  },
  documents: {
    label: 'Documents',
    goal: 'Fast path into the 8 most recently updated library artifacts.',
    provenance: 'documents[] — newest non-archived docs by updated_at.',
    action: 'Click a row to open the document editor.',
  },
  globe_scene: {
    label: 'Globe Scene',
    goal: 'Spatial map of Odysseus branches and MemPalace graph.',
    provenance: 'globe_graph + branch_health → Three.js scene (cmdCenterScene.js).',
    action: 'Orbit, hover nodes for summary, click to jump to a branch.',
  },
  stage_cards: {
    label: 'Stage Cards',
    goal: 'One-tap ritual shortcuts — CEO brief, morning report, relay, plan, sync, up next.',
    provenance: 'stage_cards[] — agenda, jobs, handoffs, plan note at build time.',
    action: 'Click a float card to run ceo_brief, jobs, agent_bin, plan, refresh, or calendar.',
  },
  hero: {
    label: 'Hero Directive',
    goal: 'Primary directive — know what is on fire within 5 seconds.',
    provenance: 'hero — relay handoffs → agency jobs → top directive → notes fallback.',
    action: 'Click overlay or CTA to act on the top-ranked item.',
  },
  command_deck: {
    label: 'Command Deck',
    goal: 'Explicit operator controls and Mycelia dispatch buttons.',
    provenance: 'commands[] + suggested_commands[] — fixed deck plus hero-branch suggestions.',
    action: 'Click a button to run the mapped _runAction (notes, tasks, run_task, etc.).',
  },
  audio_io: {
    label: 'Audio I/O',
    goal: 'Voice delegate without leaving the vault.',
    provenance: 'audio label from API; live state from voice UI events.',
    action: 'Click to arm voice agent mode (Space hold also works).',
  },
  ai_wire: {
    label: 'AI Wire',
    goal: 'Live activity ticker — traceability for what just happened.',
    provenance: 'wire[] — recent notes, docs, handoffs, jobs, sessions (newest first).',
    action: 'Click a line to open the source note, doc, handoff, or session.',
  },
};

const CMD_VIS_TOGGLABLE = [
  'status_pills', 'vitals', 'priority_queue', 'swarm_activity', 'documents',
  'globe_scene', 'stage_cards', 'hero', 'command_deck', 'audio_io', 'ai_wire',
];

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
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    const days = Math.floor(hrs / 24);
    return `${days}d`;
  } catch {
    return '';
  }
}

function _syncLabel() {
  if (_fetchError) return 'sync failed';
  if (!_syncedAt) return 'syncing…';
  const rel = _formatRelative(_syncedAt);
  return rel ? `synced ${rel} ago` : 'synced';
}

function _loadVisPrefs() {
  try {
    const raw = localStorage.getItem(VIS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function _saveVisPrefs(prefs) {
  try {
    localStorage.setItem(VIS_STORAGE_KEY, JSON.stringify(prefs));
  } catch { /* ignore quota */ }
}

function _isComponentVisible(id, prefs) {
  const p = prefs ?? _loadVisPrefs();
  return p[id] !== false;
}

function _resetVisPrefs() {
  try {
    localStorage.removeItem(VIS_STORAGE_KEY);
  } catch { /* ignore */ }
}

function _panelHeader(title, visId) {
  const meta = CMD_COMPONENT_ATLAS[visId];
  if (!meta) return `<div class="cmd-panel-h">${_esc(title)}</div>`;
  return `<div class="cmd-panel-h">
    <span class="cmd-panel-h-title">${_esc(title)}</span>
    <button type="button" class="cmd-info-btn" data-cmd-info="${_esc(visId)}" aria-label="About ${ _esc(title)}">ⓘ</button>
  </div>`;
}

function _renderVisSettingsList() {
  return CMD_VIS_TOGGLABLE.map((id) => {
    const meta = CMD_COMPONENT_ATLAS[id];
    const on = _isComponentVisible(id);
    return `
      <label class="cmd-vis-row">
        <input type="checkbox" class="cmd-vis-chk" data-vis-id="${_esc(id)}" ${on ? 'checked' : ''} />
        <span class="cmd-vis-row-text">
          <span class="cmd-vis-row-label">${_esc(meta?.label || id)}</span>
          <span class="cmd-vis-row-goal">${_esc(meta?.goal || '')}</span>
        </span>
      </label>`;
  }).join('');
}

function _renderVisSettingsDrawer() {
  return `
    <div class="cmd-vis-backdrop" id="cmd-vis-backdrop" hidden aria-hidden="true"></div>
    <div class="cmd-vis-drawer" id="cmd-vis-drawer" aria-hidden="true" role="dialog" aria-label="Vault display settings">
      <div class="cmd-vis-drawer-h">
        <span>Display</span>
        <button type="button" class="cmd-vis-close" id="cmd-vis-close" aria-label="Close display settings">✕</button>
      </div>
      <p class="cmd-vis-drawer-sub">Show or hide HUD panels. Chrome (clock, sync, minimize) stays visible.</p>
      <div class="cmd-vis-drawer-list" id="cmd-vis-drawer-list">${_renderVisSettingsList()}</div>
      <div class="cmd-vis-drawer-foot">
        <button type="button" class="cmd-vis-reset" id="cmd-vis-reset">Reset defaults</button>
        <button type="button" class="cmd-vis-done" id="cmd-vis-done">Done</button>
      </div>
    </div>
    <div class="cmd-info-popover" id="cmd-info-popover" role="dialog" aria-hidden="true" hidden></div>
  `;
}

function _tabHasVisiblePanel(root, tab) {
  const nodes = root.querySelectorAll(`[data-tab="${tab}"][data-cmd-vis]`);
  for (const node of nodes) {
    if (node.dataset.cmdHidden !== 'true') return true;
  }
  if (tab === 'hud') {
    const extras = ['cmd-status-strip', 'cmd-scene-mount', 'cmd-stage-cards-wrap', 'cmd-hero'];
    for (const id of extras) {
      const el = document.getElementById(id);
      if (el && el.dataset.cmdHidden !== 'true') return true;
    }
  }
  return false;
}

function _updateMobileEmptyHints(root) {
  const host = root || document.getElementById('cmd-center-root');
  if (!host) return;
  host.querySelectorAll('.cmd-tab-empty').forEach((el) => el.remove());
  if (!_isMobileViewport()) return;
  ['hud', 'queue', 'commands', 'wire'].forEach((tab) => {
    if (_tabHasVisiblePanel(host, tab)) return;
    if (host.dataset.mobileTab !== tab) return;
    const grid = host.querySelector('.cmd-grid');
    if (!grid) return;
    const hint = document.createElement('div');
    hint.className = 'cmd-tab-empty';
    hint.dataset.tabEmpty = tab;
    hint.innerHTML = 'All panels hidden — open <button type="button" class="cmd-tab-empty-link" data-open-vis-settings>Display settings</button>.';
    grid.appendChild(hint);
  });
}

function _railHasVisiblePanels(rail) {
  if (!rail) return false;
  const panels = rail.querySelectorAll('[data-cmd-vis]');
  if (!panels.length) return false;
  return Array.from(panels).some((el) => el.dataset.cmdHidden !== 'true');
}

function _updateRailLayout(host) {
  const grid = host.querySelector('.cmd-grid');
  if (!grid) return;
  const leftRail = grid.querySelector('.cmd-rail[data-cmd-rail="left"]');
  const rightRail = grid.querySelector('.cmd-rail[data-cmd-rail="right"]');
  const leftVisible = _railHasVisiblePanels(leftRail);
  const rightVisible = _railHasVisiblePanels(rightRail);
  if (leftRail) leftRail.dataset.railHidden = leftVisible ? 'false' : 'true';
  if (rightRail) rightRail.dataset.railHidden = rightVisible ? 'false' : 'true';
  grid.dataset.leftRail = leftVisible ? 'visible' : 'hidden';
  grid.dataset.rightRail = rightVisible ? 'visible' : 'hidden';
}

function _applyVisibilityPrefs(root) {
  const host = root || document.getElementById('cmd-center-root');
  if (!host) return;
  const prefs = _loadVisPrefs();
  host.querySelectorAll('[data-cmd-vis]').forEach((node) => {
    const id = node.dataset.cmdVis;
    node.dataset.cmdHidden = _isComponentVisible(id, prefs) ? 'false' : 'true';
  });
  _updateRailLayout(host);
  _updateMobileEmptyHints(host);
  requestAnimationFrame(_updateCardAnchors);
}

function _openVisSettings() {
  const drawer = document.getElementById('cmd-vis-drawer');
  const backdrop = document.getElementById('cmd-vis-backdrop');
  const list = document.getElementById('cmd-vis-drawer-list');
  if (!drawer || !backdrop) return;
  if (list) list.innerHTML = _renderVisSettingsList();
  drawer.setAttribute('aria-hidden', 'false');
  backdrop.hidden = false;
  backdrop.setAttribute('aria-hidden', 'false');
}

function _closeVisSettings() {
  const drawer = document.getElementById('cmd-vis-drawer');
  const backdrop = document.getElementById('cmd-vis-backdrop');
  if (!drawer || !backdrop) return;
  drawer.setAttribute('aria-hidden', 'true');
  backdrop.hidden = true;
  backdrop.setAttribute('aria-hidden', 'true');
  _hideInfoPopover();
}

function _showInfoPopover(visId, anchorEl) {
  const pop = document.getElementById('cmd-info-popover');
  const meta = CMD_COMPONENT_ATLAS[visId];
  if (!pop || !meta || !anchorEl) return;
  pop.innerHTML = `
    <div class="cmd-info-popover-h">${_esc(meta.label)}</div>
    <div class="cmd-info-popover-row"><span class="cmd-info-k">Goal</span>${_esc(meta.goal)}</div>
    <div class="cmd-info-popover-row"><span class="cmd-info-k">Provenance</span>${_esc(meta.provenance)}</div>
    <div class="cmd-info-popover-row"><span class="cmd-info-k">Action</span>${_esc(meta.action)}</div>
    <button type="button" class="cmd-info-popover-close" data-cmd-info-close aria-label="Close">✕</button>
  `;
  pop.hidden = false;
  pop.setAttribute('aria-hidden', 'false');
  const rect = anchorEl.getBoundingClientRect();
  const rootRect = document.getElementById('cmd-center-root')?.getBoundingClientRect();
  const top = rootRect ? rect.bottom - rootRect.top + 6 : rect.bottom + 6;
  const left = rootRect ? Math.min(rect.left - rootRect.left, (rootRect.width || 320) - 280) : rect.left;
  pop.style.top = `${Math.max(8, top)}px`;
  pop.style.left = `${Math.max(8, left)}px`;
}

function _hideInfoPopover() {
  const pop = document.getElementById('cmd-info-popover');
  if (!pop) return;
  pop.hidden = true;
  pop.setAttribute('aria-hidden', 'true');
  pop.innerHTML = '';
}

function _wireVisSettings(root) {
  if (_visSettingsWired) return;
  _visSettingsWired = true;
  root.addEventListener('click', (e) => {
    if (e.target.closest('#cmd-center-settings') || e.target.closest('[data-open-vis-settings]')) {
      e.preventDefault();
      e.stopPropagation();
      _openVisSettings();
      return;
    }
    if (e.target.closest('#cmd-vis-close') || e.target.closest('#cmd-vis-done') || e.target.closest('#cmd-vis-backdrop')) {
      e.preventDefault();
      _closeVisSettings();
      return;
    }
    if (e.target.closest('#cmd-vis-reset')) {
      e.preventDefault();
      _resetVisPrefs();
      _applyVisibilityPrefs(root);
      const list = document.getElementById('cmd-vis-drawer-list');
      if (list) list.innerHTML = _renderVisSettingsList();
      return;
    }
    if (e.target.closest('[data-cmd-info-close]')) {
      e.preventDefault();
      _hideInfoPopover();
    }
  });
  root.addEventListener('change', (e) => {
    const chk = e.target.closest('.cmd-vis-chk');
    if (!chk) return;
    const id = chk.dataset.visId;
    if (!id) return;
    const prefs = _loadVisPrefs();
    prefs[id] = chk.checked;
    _saveVisPrefs(prefs);
    _applyVisibilityPrefs(root);
  });
}

function _wireInfoPopovers(root) {
  if (_infoPopoverWired) return;
  _infoPopoverWired = true;
  root.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cmd-info]');
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      const id = btn.dataset.cmdInfo;
      if (id) _showInfoPopover(id, btn);
      return;
    }
    if (!e.target.closest('#cmd-info-popover') && !e.target.closest('[data-cmd-info]')) {
      _hideInfoPopover();
    }
  });
}

function _ensureStyles() {
  if (!document.getElementById('cmd-center-font')) {
    const link = document.createElement('link');
    link.id = 'cmd-center-font';
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap';
    document.head.appendChild(link);
  }
  if (document.getElementById('cmd-center-styles')) return;
  const style = document.createElement('style');
  style.id = 'cmd-center-styles';
  style.textContent = `
#${PANE_ID} {
  font-family: "JetBrains Mono", "Space Mono", ui-monospace, monospace;
}
.cmd-center-root {
  position: relative; width: 100%; height: 100%; flex: 1; min-height: 0;
  background: #050705; color: #a6e22e;
  overflow: hidden; display: flex; flex-direction: column;
  letter-spacing: 0.06em;
}
.cmd-center-root::before {
  content: ""; pointer-events: none; position: absolute; inset: 0; z-index: 5;
  background: repeating-linear-gradient(to bottom, rgba(166,226,46,0.03) 0px, rgba(166,226,46,0.03) 1px, transparent 2px, transparent 4px);
  mix-blend-mode: screen; opacity: 0.45;
}
.cmd-center-root::after {
  content: ""; pointer-events: none; position: absolute; inset: 0; z-index: 4;
  box-shadow: inset 0 0 120px rgba(0,0,0,0.85), inset 0 0 40px rgba(166,226,46,0.05);
}

.cmd-topbar {
  position: relative; z-index: 6;
  display: flex; align-items: center; gap: 12px;
  padding: 12px 18px;
  border-bottom: 1px solid rgba(166,226,46,0.22);
  background: rgba(5,10,5,0.92);
}
.cmd-brand { display: flex; flex-direction: column; min-width: 0; }
.cmd-brand-title { font-size: 18px; font-weight: 700; letter-spacing: 0.28em; text-shadow: 0 0 12px rgba(166,226,46,0.45); }
.cmd-brand-sub { font-size: 10px; opacity: 0.55; letter-spacing: 0.18em; text-transform: uppercase; }
.cmd-status-row { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; justify-content: center; }
.cmd-pill {
  border: 1px solid rgba(166,226,46,0.28); background: rgba(166,226,46,0.04); color: #a6e22e;
  font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase;
  padding: 4px 8px; border-radius: 2px; cursor: pointer;
}
.cmd-pill:hover { background: rgba(166,226,46,0.12); box-shadow: 0 0 8px rgba(166,226,46,0.25); }
.cmd-pill[data-state="online"], .cmd-pill[data-state="alive"] { box-shadow: 0 0 8px rgba(166,226,46,0.25); }
.cmd-pill[data-state="busy"] { color: #7fff00; border-color: rgba(255,107,107,0.55); animation: cmdPillPulse 1.4s ease-in-out infinite; }
.cmd-pill[data-state="idle"] { opacity: 0.55; }
@keyframes cmdPillPulse { 0%,100%{ opacity:1; } 50%{ opacity:0.65; } }
.cmd-clock-wrap { display: flex; flex-direction: column; align-items: flex-end; min-width: 100px; }
.cmd-clock { font-size: 20px; font-weight: 700; letter-spacing: 0.14em; text-align: right; text-shadow: 0 0 10px rgba(166,226,46,0.35); }
.cmd-date { font-size: 9px; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.55; }
.cmd-sync { font-size: 8px; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.5; cursor: pointer; margin-top: 2px; }
.cmd-sync[data-stale="true"] { color: #ffb347; opacity: 0.85; }
.cmd-mobile-grabber { display: none; }
.cmd-minimize {
  border: 1px solid rgba(166,226,46,0.3); background: transparent; color: #a6e22e;
  width: 28px; height: 28px; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
}
.cmd-minimize:hover { background: rgba(166,226,46,0.12); box-shadow: 0 0 10px rgba(166,226,46,0.25); }

.cmd-grid {
  position: relative; z-index: 6;
  display: flex; align-items: stretch;
  gap: 12px; padding: 12px; min-height: 0; flex: 1;
}
.cmd-rail[data-cmd-rail="left"],
.cmd-rail[data-cmd-rail="right"] {
  flex: 0 1 280px; min-width: 240px; max-width: 320px;
}
.cmd-rail[data-rail-hidden="true"] { display: none !important; }
.cmd-stage { flex: 1 1 360px; min-width: 0; }
.cmd-panel {
  border: 1px solid rgba(166,226,46,0.18); background: rgba(8,14,8,0.72);
  box-shadow: 0 0 18px rgba(0,0,0,0.35), inset 0 0 24px rgba(166,226,46,0.03);
  display: flex; flex-direction: column; min-height: 0;
}
.cmd-panel-h {
  font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; padding: 8px 10px;
  border-bottom: 1px solid rgba(166,226,46,0.14); opacity: 0.8;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.cmd-panel-h-title { flex: 1; min-width: 0; }
.cmd-panel-b { padding: 8px 10px; overflow: auto; flex: 1; min-height: 0; }
.cmd-rail { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.cmd-rail .cmd-panel { flex: 1; }

.cmd-vital {
  display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center;
  padding: 6px 0; border-bottom: 1px solid rgba(166,226,46,0.08); cursor: pointer;
}
.cmd-vital:hover { background: rgba(166,226,46,0.05); }
.cmd-vital-label { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; opacity: 0.75; }
.cmd-vital-val { font-size: 13px; font-weight: 600; text-align: right; }
.cmd-vital-delta { font-size: 9px; opacity: 0.5; grid-column: 1 / -1; margin-top: -4px; }

.cmd-dir-item, .cmd-doc-item {
  display: flex; gap: 8px; align-items: baseline; padding: 6px 0;
  border-bottom: 1px solid rgba(166,226,46,0.07); cursor: pointer; font-size: 11px;
}
.cmd-dir-item:hover, .cmd-doc-item:hover { color: #7fff00; text-shadow: 0 0 8px rgba(127,255,0,0.35); }
.cmd-dir-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; background: #a6e22e; }
.cmd-dir-dot[data-branch="relay"] { background: #ff6b6b; box-shadow: 0 0 6px rgba(255,107,107,0.6); }
.cmd-dir-dot[data-branch="agency"] { background: #7fff00; }
.cmd-dir-num { opacity: 0.45; min-width: 18px; }
.cmd-dir-title, .cmd-doc-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cmd-dir-meta, .cmd-doc-meta { font-size: 9px; opacity: 0.5; letter-spacing: 0.08em; }

.cmd-stage {
  position: relative; border: 1px solid rgba(166,226,46,0.18);
  background: radial-gradient(circle at center, rgba(80,255,120,.07), rgba(5,10,6,.64) 42%, rgba(4,8,5,.92) 75%);
  min-height: 0; overflow: hidden; display: flex; flex-direction: column;
}
.cmd-stage::before {
  content: "";
  position: absolute; inset: auto 0 0 0; height: 38%; z-index: 0;
  background:
    linear-gradient(rgba(0,0,0,0), rgba(0,0,0,.45)),
    linear-gradient(to right, transparent 0%, rgba(120,255,145,.07) 30%, rgba(120,255,145,.07) 70%, transparent 100%),
    repeating-linear-gradient(to right, rgba(115,255,146,.1) 0, rgba(115,255,146,.1) 1px, transparent 1px, transparent 44px),
    repeating-linear-gradient(to top, rgba(115,255,146,.1) 0, rgba(115,255,146,.1) 1px, transparent 1px, transparent 28px);
  transform: perspective(700px) rotateX(72deg);
  transform-origin: bottom center;
  opacity: .7;
  pointer-events: none;
}
#cmd-scene-mount { position: absolute; inset: 0; z-index: 1; }
#cmd-scene-mount canvas { display: block; width: 100% !important; height: 100% !important; cursor: grab; touch-action: none; }
.cmd-scene-tooltip {
  position: absolute; z-index: 4; pointer-events: none; max-width: 220px;
  padding: 6px 10px; border-radius: 4px; font: 11px/1.35 'JetBrains Mono', monospace;
  color: #e8ffe8; background: rgba(8,18,10,0.88); border: 1px solid rgba(127,255,0,0.25);
  box-shadow: 0 4px 16px rgba(0,0,0,0.45); opacity: 0; transition: opacity 0.12s ease;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cmd-scene-popup {
  position: absolute; z-index: 6; min-width: 200px; max-width: 280px; pointer-events: auto;
  padding: 10px 12px 9px; border-radius: 3px;
  font: 12px/1.5 'JetBrains Mono', 'Consolas', monospace; color: #b6ff6e;
  background: rgba(6,14,8,0.96); border: 1px solid rgba(127,255,0,0.55);
  box-shadow: 0 6px 22px rgba(0,0,0,0.55), 0 0 14px rgba(127,255,0,0.18);
  text-shadow: 0 0 6px rgba(127,255,0,0.45); opacity: 0; transition: opacity 0.14s ease;
  user-select: none;
}
.cmd-scene-popup[aria-hidden="false"] { opacity: 1; }
.cmd-scene-popup-h {
  font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: #7fff00;
  padding-bottom: 5px; margin-bottom: 6px; border-bottom: 1px solid rgba(127,255,0,0.25);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cmd-scene-popup-line { white-space: pre-wrap; word-break: break-word; }
.cmd-scene-popup-label { color: #e8ffe8; }
.cmd-scene-popup-summary { opacity: 0.92; margin-top: 2px; }
.cmd-scene-popup-meta { font-size: 10px; opacity: 0.6; margin-top: 4px; letter-spacing: 0.06em; }
.cmd-scene-popup-cta {
  margin-top: 8px; font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase;
  color: #7fff00; border: 1px solid rgba(127,255,0,0.45); padding: 4px 8px; display: inline-block;
  cursor: pointer; user-select: none;
}
.cmd-scene-popup-cta:hover { background: rgba(127,255,0,0.12); box-shadow: 0 0 10px rgba(127,255,0,0.35); }
.cmd-scene-auto {
  position: absolute; top: 10px; right: 12px; z-index: 5; pointer-events: auto;
  font: 10px/1 'JetBrains Mono', monospace; letter-spacing: 0.16em; text-transform: uppercase;
  color: #7fff00; border: 1px solid rgba(127,255,0,0.35); padding: 5px 8px; cursor: pointer;
  background: rgba(6,14,8,0.7); user-select: none;
}
.cmd-scene-auto:hover { box-shadow: 0 0 10px rgba(127,255,0,0.3); }
.cmd-scene-auto[data-on="false"] { color: #6a7a6a; border-color: rgba(120,140,120,0.3); }

.cmd-float-card {
  position: absolute; z-index: 2; border: 1px solid rgba(166,226,46,0.35);
  background: rgba(5,10,5,0.78); padding: 8px 10px; min-width: 120px; max-width: 180px;
  cursor: pointer; box-shadow: 0 0 14px rgba(166,226,46,0.12); backdrop-filter: blur(2px);
}
.cmd-float-card:hover { box-shadow: 0 0 18px rgba(166,226,46,0.35); color: #7fff00; }
.cmd-float-card[data-pos="tl"] { top: 12%; left: 8%; }
.cmd-float-card[data-pos="tr"] { top: 18%; right: 10%; }
.cmd-float-card[data-pos="bl"] { bottom: 28%; left: 10%; }
.cmd-float-card[data-pos="br"] { bottom: 30%; right: 8%; }
.cmd-float-card[data-pos="ml"] { top: 46%; left: 5%; }
.cmd-float-label { font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; opacity: 0.7; }
.cmd-float-sub { font-size: 10px; margin-top: 4px; opacity: 0.85; line-height: 1.3; }

.cmd-hero {
  position: relative; z-index: 2; margin-top: auto; padding: 14px 16px 16px;
  border-top: 1px solid rgba(166,226,46,0.18);
  background: linear-gradient(to top, rgba(5,10,5,0.92), rgba(5,10,5,0.35)); cursor: pointer;
}
.cmd-hero-label { font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.7; }
.cmd-hero-title { font-size: 12px; margin-top: 4px; opacity: 0.9; }
.cmd-hero-value { font-size: 34px; font-weight: 700; letter-spacing: 0.08em; margin-top: 6px; text-shadow: 0 0 18px rgba(166,226,46,0.45); }
.cmd-hero-unit { font-size: 12px; letter-spacing: 0.18em; margin-left: 8px; opacity: 0.7; }
.cmd-hero-explain { font-size: 10px; opacity: 0.65; margin-top: 6px; line-height: 1.4; max-width: 520px; }
.cmd-hero-vel { font-size: 10px; opacity: 0.55; margin-top: 4px; letter-spacing: 0.1em; }
.cmd-hero-cta {
  display: inline-block; margin-top: 8px; font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
  border: 1px solid rgba(166,226,46,0.35); padding: 5px 10px; opacity: 0.85;
}

.cmd-suggested { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.cmd-suggest-btn {
  border: 1px solid rgba(127,255,0,0.35); background: rgba(127,255,0,0.08); color: #7fff00;
  font: inherit; font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
  padding: 6px 8px; cursor: pointer;
}
.cmd-suggest-btn:hover { background: rgba(127,255,0,0.16); }

.cmd-cmds { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.cmd-cmd-group { grid-column: 1 / -1; font-size: 8px; letter-spacing: 0.28em; text-transform: uppercase; opacity: 0.45; margin-top: 4px; }
.cmd-cmd-group:first-child { margin-top: 0; }
.cmd-cmd-btn {
  border: 1px solid rgba(166,226,46,0.28); background: rgba(166,226,46,0.04); color: #a6e22e;
  font: inherit; font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase;
  padding: 10px 8px; cursor: pointer; text-align: left;
}
.cmd-cmd-btn:hover { background: rgba(166,226,46,0.12); box-shadow: 0 0 12px rgba(166,226,46,0.28); color: #7fff00; }

.cmd-audio {
  display: flex; align-items: center; gap: 10px; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
  cursor: pointer; border: 1px solid transparent; padding: 6px 8px; margin: -6px -8px; border-radius: 4px;
  transition: border-color 0.15s, background 0.15s;
}
.cmd-audio:hover { border-color: rgba(166,226,46,0.35); background: rgba(166,226,46,0.06); }
.cmd-audio:focus-visible { outline: 2px solid rgba(166,226,46,0.55); outline-offset: 2px; }
.cmd-audio-dot { width: 8px; height: 8px; border-radius: 50%; background: #a6e22e; box-shadow: 0 0 8px rgba(166,226,46,0.6); animation: cmdPulse 1.6s ease-in-out infinite; }
.cmd-audio-lock {
  margin-left: auto; font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
  padding: 3px 7px; border: 1px solid rgba(166,226,46,0.35); background: transparent;
  color: #a6e22e; cursor: pointer; border-radius: 3px; font-family: inherit;
}
.cmd-audio-lock:hover { background: rgba(166,226,46,0.12); }
@keyframes cmdPulse { 0%,100%{ opacity:0.45; } 50%{ opacity:1; } }
.cmd-audio-hint { margin-top: 6px; font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; opacity: 0.55; }
.cmd-audio[data-state="listening"] .cmd-audio-dot, .cmd-audio[data-state="speaking"] .cmd-audio-dot {
  background: #7fff00; box-shadow: 0 0 12px rgba(127,255,0,0.8); animation: cmdPulse 0.7s ease-in-out infinite;
}

.cmd-wire { display: flex; flex-direction: column; gap: 6px; font-size: 10px; line-height: 1.35; }
.cmd-wire-item { border-left: 2px solid rgba(166,226,46,0.25); padding-left: 8px; opacity: 0.8; cursor: pointer; display: flex; gap: 8px; }
.cmd-wire-item:hover { opacity: 1; color: #7fff00; }
.cmd-wire-ts { opacity: 0.45; min-width: 28px; font-size: 9px; }
.cmd-wire-tag { opacity: 0.55; font-size: 8px; letter-spacing: 0.12em; min-width: 36px; }
.cmd-empty { opacity: 0.45; font-size: 10px; padding: 8px 0; }
.cmd-error-banner {
  position: relative; z-index: 7; padding: 8px 14px;
  border-bottom: 1px solid rgba(255,80,80,0.35); background: rgba(40,8,8,0.85); color: #ff8a8a;
  font-size: 10px; letter-spacing: 0.1em; display: flex; align-items: center; gap: 12px; justify-content: space-between;
}
.cmd-error-banner button {
  border: 1px solid rgba(255,138,138,0.45); background: transparent; color: #ff8a8a;
  font: inherit; font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase; padding: 4px 8px; cursor: pointer;
}

.cmd-tabs { display: none; }
.cmd-status-strip { display: none; }

@media (max-width: 1100px) {
  .cmd-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
  }
  .cmd-rail[data-cmd-rail="left"],
  .cmd-rail[data-cmd-rail="right"] { flex: unset; max-width: none; }
  .cmd-stage { grid-column: 1 / -1; min-height: 360px; flex: unset; }
}
@media (max-width: 720px) {
  .cmd-grid {
    grid-template-columns: 1fr;
    display: grid;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 8px; gap: 8px;
  }
  .cmd-status-row { display: none; }

  .cmd-tabs {
    display: flex; position: relative; z-index: 6;
    border-bottom: 1px solid rgba(166,226,46,0.22);
    background: rgba(5,10,5,0.92);
  }
  .cmd-tab {
    flex: 1 1 0; border: none; background: transparent; color: #a6e22e;
    font: inherit; font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase;
    padding: 12px 4px; cursor: pointer; opacity: 0.5;
    border-bottom: 2px solid transparent;
  }
  .cmd-tab[aria-pressed="true"] { opacity: 1; border-bottom-color: #7fff00; }
  .cmd-tab:active { background: rgba(166,226,46,0.08); }

  .cmd-status-strip {
    display: flex; gap: 6px; overflow-x: auto; padding: 8px 12px;
    border-bottom: 1px solid rgba(166,226,46,0.12);
  }
  .cmd-status-strip .cmd-pill { flex-shrink: 0; }

  .cmd-center-root[data-mobile-tab="hud"] .cmd-grid [data-tab]:not([data-tab="hud"]) { display: none; }
  .cmd-center-root[data-mobile-tab="queue"] .cmd-grid [data-tab]:not([data-tab="queue"]) { display: none; }
  .cmd-center-root[data-mobile-tab="commands"] .cmd-grid [data-tab]:not([data-tab="commands"]) { display: none; }
  .cmd-center-root[data-mobile-tab="wire"] .cmd-grid [data-tab]:not([data-tab="wire"]) { display: none; }
  .cmd-center-root:not([data-mobile-tab="hud"]) .cmd-status-strip { display: none; }

  .cmd-float-card { display: none !important; }
  .cmd-stage { min-height: 58vh; }
  .cmd-hero-value { font-size: 28px; }
  .cmd-topbar { padding: 10px 12px; gap: 8px; }
  .cmd-brand-title { font-size: 15px; letter-spacing: 0.22em; }
  .cmd-brand-sub { display: none; }
  .cmd-clock { font-size: 16px; }
  .cmd-clock-wrap { min-width: 80px; }
  .cmd-rail { gap: 8px; }
  .cmd-panel { border-radius: 0; }
  .cmd-cmds { grid-template-columns: 1fr 1fr; }
}

[data-cmd-vis][data-cmd-hidden="true"] { display: none !important; }

.cmd-info-btn {
  flex-shrink: 0; border: 1px solid rgba(166,226,46,0.25); background: transparent;
  color: #a6e22e; font-size: 11px; line-height: 1; width: 22px; height: 22px;
  border-radius: 4px; cursor: pointer; opacity: 0.75; padding: 0;
}
.cmd-info-btn:hover { opacity: 1; box-shadow: 0 0 8px rgba(127,255,0,0.25); }

.cmd-settings-btn {
  position: relative; z-index: 7; flex-shrink: 0;
  width: 32px; height: 32px; border-radius: 6px;
  border: 1px solid rgba(166,226,46,0.28); background: rgba(5,10,5,0.85);
  color: #a6e22e; cursor: pointer; display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
}
.cmd-settings-btn:hover { box-shadow: 0 0 10px rgba(127,255,0,0.35); color: #7fff00; }

.cmd-vis-backdrop {
  position: absolute; inset: 0; z-index: 20; background: rgba(0,0,0,0.55);
}
.cmd-vis-drawer {
  position: absolute; top: 56px; right: 12px; z-index: 21;
  width: min(360px, calc(100% - 24px)); max-height: calc(100% - 72px);
  display: flex; flex-direction: column;
  background: rgba(8,14,8,0.98); border: 1px solid rgba(166,226,46,0.35);
  box-shadow: 0 12px 40px rgba(0,0,0,0.65), 0 0 24px rgba(166,226,46,0.08);
  border-radius: 8px; overflow: hidden;
}
.cmd-vis-drawer[aria-hidden="true"] { display: none; }
.cmd-vis-drawer-h {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
  border-bottom: 1px solid rgba(166,226,46,0.18);
}
.cmd-vis-close {
  border: none; background: transparent; color: #a6e22e; cursor: pointer; font-size: 14px; opacity: 0.7;
}
.cmd-vis-close:hover { opacity: 1; }
.cmd-vis-drawer-sub {
  margin: 0; padding: 10px 14px 0; font-size: 10px; line-height: 1.45; opacity: 0.65;
}
.cmd-vis-drawer-list {
  padding: 10px 14px; overflow: auto; flex: 1; min-height: 0;
  display: flex; flex-direction: column; gap: 8px;
}
.cmd-vis-row {
  display: flex; gap: 10px; align-items: flex-start; cursor: pointer; font-size: 10px; line-height: 1.4;
}
.cmd-vis-chk { margin-top: 2px; accent-color: #7fff00; flex-shrink: 0; }
.cmd-vis-row-label { display: block; letter-spacing: 0.08em; color: #e8ffe8; }
.cmd-vis-row-goal { display: block; opacity: 0.6; margin-top: 2px; font-size: 9px; line-height: 1.35; }
.cmd-vis-drawer-foot {
  display: flex; gap: 8px; padding: 10px 14px 12px; border-top: 1px solid rgba(166,226,46,0.18);
}
.cmd-vis-reset, .cmd-vis-done {
  flex: 1; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
  padding: 8px 10px; border-radius: 4px; cursor: pointer; font-family: inherit;
}
.cmd-vis-reset {
  border: 1px solid rgba(166,226,46,0.25); background: transparent; color: #a6e22e;
}
.cmd-vis-done {
  border: 1px solid rgba(127,255,0,0.45); background: rgba(127,255,0,0.12); color: #7fff00;
}

.cmd-info-popover {
  position: absolute; z-index: 22; width: min(280px, calc(100% - 24px));
  background: rgba(8,14,8,0.98); border: 1px solid rgba(166,226,46,0.4);
  border-radius: 6px; padding: 10px 12px 12px; font-size: 10px; line-height: 1.45;
  box-shadow: 0 8px 28px rgba(0,0,0,0.6);
}
.cmd-info-popover-h {
  font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
  margin-bottom: 8px; color: #7fff00;
}
.cmd-info-popover-row { margin-bottom: 6px; }
.cmd-info-k {
  display: block; font-size: 8px; letter-spacing: 0.16em; text-transform: uppercase;
  opacity: 0.55; margin-bottom: 2px;
}
.cmd-info-popover-close {
  position: absolute; top: 6px; right: 6px; border: none; background: transparent;
  color: #a6e22e; cursor: pointer; opacity: 0.65; font-size: 12px;
}

.cmd-tab-empty {
  grid-column: 1 / -1; padding: 24px 16px; text-align: center;
  font-size: 11px; opacity: 0.75; line-height: 1.5;
}
.cmd-tab-empty-link {
  border: none; background: none; color: #7fff00; cursor: pointer;
  font-family: inherit; font-size: inherit; text-decoration: underline; padding: 0;
}

.cmd-stage-cards-wrap { position: absolute; inset: 0; z-index: 2; pointer-events: none; }
.cmd-stage-cards-wrap .cmd-float-card { pointer-events: auto; }
`;
  document.head.appendChild(style);
}

async function _fetchData({ syncCalendar = false } = {}) {
  try {
    const qs = syncCalendar ? '?sync_calendar=1' : '';
    const res = await fetch(`${API_BASE}/api/home/cmd-center${qs}`, { credentials: 'same-origin' });
    if (res.status === 401) {
      _fetchError = 'Session expired — reload and sign in, then Vault Sync.';
      throw new Error('cmd-center 401');
    }
    if (res.status === 404) {
      _fetchError = 'CMD Center API missing — rebuild the Odysseus container.';
      throw new Error('cmd-center 404');
    }
    if (!res.ok) throw new Error(`cmd-center ${res.status}`);
    const payload = await res.json();
    _data = { ...DATA, ...payload };
    _syncedAt = payload.synced_at || new Date().toISOString();
    _fetchError = null;
  } catch (err) {
    console.warn('CMD Center fetch failed', err);
    if (!_fetchError) _fetchError = `Sync failed (${err.message || 'network'}) — click Vault Sync.`;
    if (!(_data.vitals && _data.vitals.length)) _data = { ...DATA };
  }
}

function _renderVitals(list) {
  if (!list?.length) return '<div class="cmd-empty">No vitals yet</div>';
  return list.map((v) => {
    // Surface actions (notes/library/tasks) must NOT pass the vital's category
    // key as data-id — that was treated as a note/doc id and spawned races.
    const targetId = v.target_id || '';
    const idAttr = targetId ? ` data-id="${_esc(targetId)}"` : '';
    return `
    <div class="cmd-vital" data-action="${_esc(v.action || '')}"${idAttr}>
      <div class="cmd-vital-label">${_esc(v.label)}</div>
      <div class="cmd-vital-val">${_esc(v.display ?? v.value)}</div>
      <div class="cmd-vital-delta">${_esc(v.delta || '')}</div>
    </div>
  `;
  }).join('');
}

function _renderDirectives(list) {
  if (!list?.length) return '<div class="cmd-empty">Clear deck — nothing queued</div>';
  return list.map((d, i) => `
    <div class="cmd-dir-item" data-action="${_esc(d.action || '')}" data-id="${_esc(d.target_id || d.id || '')}">
      <span class="cmd-dir-dot" data-branch="${_esc(d.branch || '')}"></span>
      <span class="cmd-dir-num">${String(i + 1).padStart(2, '0')}</span>
      <span class="cmd-dir-title" title="${_esc(d.title)}">${_esc(d.title)}</span>
      <span class="cmd-dir-meta">${_esc(d.meta || d.kind || '')}</span>
    </div>
  `).join('');
}

function _renderDocs(list) {
  if (!list?.length) return '<div class="cmd-empty">No documents</div>';
  return list.map((d) => {
    const rel = _formatRelative(d.updated_at);
    return `
    <div class="cmd-doc-item" data-action="${_esc(d.action || 'open_doc')}" data-id="${_esc(d.id || '')}">
      <span class="cmd-doc-title" title="${_esc(d.title)}">${_esc(d.title)}</span>
      <span class="cmd-doc-meta">${_esc(d.tag || '')}${rel ? ` · ${rel}` : ''}</span>
    </div>`;
  }).join('');
}

function _renderStatus(list) {
  return (list || []).map((s) =>
    `<button type="button" class="cmd-pill" data-state="${_esc(s.state)}" data-action="${_esc(s.action || '')}" title="${_esc(s.summary || s.label)}">${_esc(s.label)}</button>`
  ).join('');
}

function _renderSuggested(list) {
  if (!list?.length) return '';
  return `<div class="cmd-suggested">${list.map((c) => `
    <button type="button" class="cmd-suggest-btn" data-action="${_esc(c.action)}" data-id="${_esc(c.target_id || '')}">${_esc(c.label)}</button>
  `).join('')}</div>`;
}

function _renderCommands(list) {
  const cmds = list || DATA.commands;
  const groups = [];
  for (const c of cmds) {
    const name = c.group || '';
    let g = groups.find((x) => x.name === name);
    if (!g) { g = { name, items: [] }; groups.push(g); }
    g.items.push(c);
  }
  return groups.map((g) => `
    ${g.name ? `<div class="cmd-cmd-group">${_esc(g.name)}</div>` : ''}
    ${g.items.map((c) => {
      const targetId = c.target_id || '';
      const idAttr = targetId ? ` data-id="${_esc(targetId)}"` : '';
      return `<button type="button" class="cmd-cmd-btn" data-action="${_esc(c.action)}"${idAttr}>${_esc(c.label)}</button>`;
    }).join('')}
  `).join('');
}

function _renderAgentActivity(list) {
  if (!list?.length) return '<div class="cmd-empty">No agent runs yet — dispatch one from the Mycelia deck</div>';
  return `<div class="cmd-wire">${list.map((a) => `
    <div class="cmd-wire-item" data-action="${_esc(a.action || 'open_task')}" data-id="${_esc(a.target_id || '')}" data-state="${_esc(a.status || '')}">
      <span class="cmd-wire-ts">${_esc(_formatRelative(a.ts) || '—')}</span>
      <span class="cmd-wire-tag">${_esc(a.agent || 'AGENT')}</span>
      <span title="${_esc(a.text || '')}">${_esc(a.text || '')}</span>
    </div>
  `).join('')}</div>`;
}

function _renderWire(list) {
  if (!list?.length) return '<div class="cmd-empty">Wire quiet</div>';
  return `<div class="cmd-wire">${list.map((w) => `
    <div class="cmd-wire-item" data-action="${_esc(w.action || '')}" data-id="${_esc(w.target_id || '')}">
      <span class="cmd-wire-ts">${_esc(_formatRelative(w.ts) || '—')}</span>
      <span class="cmd-wire-tag">${_esc((w.branch || '').toUpperCase())}</span>
      <span>${_esc(w.text)}</span>
    </div>
  `).join('')}</div>`;
}

/** Older backends omit stage_cards[].branch — fall back by card id so the
 * globe connector lines always know which node each card belongs to. */
const CARD_BRANCH_FALLBACK = {
  morning_report: 'agency',
  agent_relay: 'relay',
  plan_today: 'prod',
  metrics_pull: 'core',
  up_next: 'comms',
};

function _cardBranch(c) {
  return c.branch || CARD_BRANCH_FALLBACK[c.id] || '';
}

function _renderStageCards(cards) {
  const positions = ['tl', 'tr', 'bl', 'br', 'ml'];
  return (cards || []).slice(0, 5).map((c, i) => `
    <div class="cmd-float-card" data-pos="${positions[i] || 'tl'}" data-action="${_esc(c.action || '')}" data-id="${_esc(c.target_id || '')}" data-branch="${_esc(_cardBranch(c))}">
      <div class="cmd-float-label">${_esc(c.label)}</div>
      <div class="cmd-float-sub">${_esc(c.subtitle || '')}</div>
    </div>
  `).join('');
}

/** True if the in-place update succeeded (same card count); otherwise the
 * caller should fall back to a full _paint() re-render. */
function _updateStageCardsInPlace(cards) {
  const stage = document.getElementById('cmd-stage');
  if (!stage) return false;
  const nodes = Array.from(stage.querySelectorAll('.cmd-float-card'));
  const list = cards || [];
  if (!nodes.length || nodes.length !== list.length) return false;
  list.forEach((c, i) => {
    const el = nodes[i];
    el.dataset.action = c.action || '';
    el.dataset.id = c.target_id || '';
    el.dataset.branch = _cardBranch(c);
    const label = el.querySelector('.cmd-float-label');
    const sub = el.querySelector('.cmd-float-sub');
    if (label) label.textContent = c.label || '';
    if (sub) sub.textContent = c.subtitle || '';
  });
  return true;
}

function _refreshHandoffPanelsInPlace(data) {
  const vitalsEl = document.getElementById('cmd-vitals');
  if (vitalsEl) vitalsEl.innerHTML = _renderVitals(data.vitals);

  const directivesEl = document.getElementById('cmd-directives');
  if (directivesEl) {
    directivesEl.innerHTML = _renderDirectives(data.directives || data.priority_queue);
  }

  const hero = data.hero || DATA.hero;
  const heroEl = document.getElementById('cmd-hero');
  if (heroEl) {
    heroEl.dataset.action = hero.action || '';
    heroEl.dataset.id = hero.target_id || '';
    const label = heroEl.querySelector('.cmd-hero-label');
    const title = heroEl.querySelector('.cmd-hero-title');
    const unit = heroEl.querySelector('.cmd-hero-unit');
    const explain = heroEl.querySelector('.cmd-hero-explain');
    const vel = heroEl.querySelector('.cmd-hero-vel');
    if (label) label.textContent = hero.label || '';
    if (title) title.textContent = hero.title || '';
    if (unit) unit.textContent = hero.unit || '';
    if (explain) explain.textContent = hero.explain || '';
    if (vel) vel.textContent = hero.velocity || '';
    let cta = heroEl.querySelector('.cmd-hero-cta');
    if (hero.cta_label) {
      if (!cta) {
        cta = document.createElement('span');
        cta.className = 'cmd-hero-cta';
        heroEl.appendChild(cta);
      }
      cta.textContent = `${hero.cta_label} →`;
    } else if (cta) {
      cta.remove();
    }
    _heroAnimated = false;
    _animateHero(hero.value || 0);
  }

  const statusRow = document.querySelector('.cmd-status-row');
  if (statusRow) statusRow.innerHTML = _renderStatus(data.status);

  const statusStrip = document.getElementById('cmd-status-strip');
  if (statusStrip) statusStrip.innerHTML = _renderStatus(data.status);

  const wireEl = document.getElementById('cmd-wire');
  if (wireEl) wireEl.innerHTML = _renderWire(data.wire);
}

/** Anchor each floating card to the edge facing the globe center, in
 * #cmd-scene-mount local pixel coordinates, so connector lines track it. */
function _updateCardAnchors() {
  const mount = document.getElementById('cmd-scene-mount');
  const stage = document.getElementById('cmd-stage');
  if (!mount || !stage) return;
  const mountRect = mount.getBoundingClientRect();
  if (!mountRect.width || !mountRect.height) return;
  const cx = mountRect.width / 2;
  const cy = mountRect.height / 2 - Math.min(24, mountRect.height * 0.04);

  const anchors = [];
  stage.querySelectorAll('.cmd-float-card[data-branch]').forEach((card) => {
    const branch = card.dataset.branch;
    if (!branch) return;
    const rect = card.getBoundingClientRect();
    if (!rect.width || !rect.height) return; // hidden (e.g. mobile) — no connector
    const cardCx = rect.left + rect.width / 2 - mountRect.left;
    const cardCy = rect.top + rect.height / 2 - mountRect.top;
    const dx = cx - cardCx;
    const dy = cy - cardCy;
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist;
    const uy = dy / dist;
    const halfW = rect.width / 2;
    const halfH = rect.height / 2;
    const tx = ux !== 0 ? halfW / Math.abs(ux) : Infinity;
    const ty = uy !== 0 ? halfH / Math.abs(uy) : Infinity;
    const t = Math.min(tx, ty);
    anchors.push({
      id: card.dataset.id || card.dataset.action || branch,
      branch,
      x: cardCx + ux * t,
      y: cardCy + uy * t,
    });
  });
  setCardAnchors(anchors);
}

function _buildHTML(data) {
  const hero = data.hero || DATA.hero;
  const audio = data.audio || DATA.audio;
  const stale = _syncedAt && (Date.now() - new Date(_syncedAt).getTime() > 60000);

  const errBanner = _fetchError
    ? `<div class="cmd-error-banner"><span>${_esc(_fetchError)}</span><button type="button" data-action="refresh">Vault Sync</button></div>`
    : '';

  return `
    <div class="cmd-center-root" id="cmd-center-root" data-mobile-tab="${_esc(_mobileTab)}">
      <div class="cmd-mobile-grabber notes-mobile-grabber" aria-hidden="true"></div>
      <header class="cmd-topbar">
        <div class="cmd-brand">
          <div class="cmd-brand-title">${_esc(data.title || DATA.title)}</div>
          <div class="cmd-brand-sub">${_esc(data.subtitle || DATA.subtitle)}</div>
        </div>
        <div class="cmd-status-row" data-cmd-vis="status_pills">${_renderStatus(data.status)}</div>
        <div class="cmd-clock-wrap">
          <div class="cmd-clock" id="cmd-center-clock">00:00:00</div>
          <div class="cmd-date" id="cmd-center-date"></div>
          <div class="cmd-sync" id="cmd-sync-label" data-action="refresh" data-stale="${stale ? 'true' : 'false'}">${_esc(_syncLabel())}</div>
        </div>
        <button type="button" class="cmd-settings-btn" id="cmd-center-settings" title="Vault display settings" aria-label="Vault display settings">⚙</button>
        <button type="button" class="modal-minimize-btn cmd-minimize" id="cmd-center-minimize" title="Minimize" aria-label="Minimize vault">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" aria-hidden="true"><line x1="6" y1="18" x2="18" y2="18"/></svg>
        </button>
      </header>
      ${errBanner}
      <nav class="cmd-tabs" id="cmd-tabs" aria-label="Vault sections">
        <button type="button" class="cmd-tab" data-tab="hud" aria-pressed="${_mobileTab === 'hud' ? 'true' : 'false'}">HUD</button>
        <button type="button" class="cmd-tab" data-tab="queue" aria-pressed="${_mobileTab === 'queue' ? 'true' : 'false'}">Queue</button>
        <button type="button" class="cmd-tab" data-tab="commands" aria-pressed="${_mobileTab === 'commands' ? 'true' : 'false'}">Commands</button>
        <button type="button" class="cmd-tab" data-tab="wire" aria-pressed="${_mobileTab === 'wire' ? 'true' : 'false'}">Wire</button>
      </nav>
      <div class="cmd-grid">
        <div class="cmd-status-strip" id="cmd-status-strip" data-tab="hud" data-cmd-vis="status_pills">${_renderStatus(data.status)}</div>
        <aside class="cmd-rail" data-cmd-rail="left">
          <section class="cmd-panel" data-tab="queue" data-cmd-vis="vitals">
            ${_panelHeader('System Vitals', 'vitals')}
            <div class="cmd-panel-b" id="cmd-vitals">${_renderVitals(data.vitals)}</div>
          </section>
          <section class="cmd-panel" data-tab="queue" data-cmd-vis="priority_queue">
            ${_panelHeader('Priority Queue', 'priority_queue')}
            <div class="cmd-panel-b" id="cmd-directives">${_renderDirectives(data.directives || data.priority_queue)}</div>
          </section>
          ${(data.agent_activity && data.agent_activity.length) ? `
          <section class="cmd-panel" data-tab="queue" data-cmd-vis="swarm_activity">
            ${_panelHeader('Swarm Activity', 'swarm_activity')}
            <div class="cmd-panel-b" id="cmd-agent-activity">${_renderAgentActivity(data.agent_activity)}</div>
          </section>` : ''}
          <section class="cmd-panel" data-tab="queue" data-cmd-vis="documents">
            ${_panelHeader('Documents', 'documents')}
            <div class="cmd-panel-b" id="cmd-documents">${_renderDocs(data.documents)}</div>
          </section>
        </aside>

        <section class="cmd-stage" id="cmd-stage" data-tab="hud">
          <div id="cmd-scene-mount" data-cmd-vis="globe_scene"></div>
          <div class="cmd-scene-auto" id="cmd-scene-auto" data-cmd-vis="globe_scene" data-on="true" role="button" tabindex="0" aria-label="Toggle globe auto-spin" title="Toggle auto-spin (double-click empty space to reset)">⟳ AUTO</div>
          <div class="cmd-stage-cards-wrap" id="cmd-stage-cards-wrap" data-cmd-vis="stage_cards" data-tab="hud">${_renderStageCards(data.stage_cards)}</div>
          <div class="cmd-hero" id="cmd-hero" data-cmd-vis="hero" data-tab="hud" data-action="${_esc(hero.action || '')}" data-id="${_esc(hero.target_id || '')}">
            <div class="cmd-hero-label">${_esc(hero.label || '')}</div>
            <div class="cmd-hero-title">${_esc(hero.title || '')}</div>
            <div class="cmd-hero-value"><span id="cmd-hero-num">0</span><span class="cmd-hero-unit">${_esc(hero.unit || '')}</span></div>
            <div class="cmd-hero-explain">${_esc(hero.explain || '')}</div>
            <div class="cmd-hero-vel">${_esc(hero.velocity || '')}</div>
            ${hero.cta_label ? `<span class="cmd-hero-cta">${_esc(hero.cta_label)} →</span>` : ''}
          </div>
        </section>

        <aside class="cmd-rail" data-cmd-rail="right">
          <section class="cmd-panel" data-tab="commands" data-cmd-vis="command_deck">
            ${_panelHeader('Command Deck', 'command_deck')}
            <div class="cmd-panel-b">
              ${_renderSuggested(data.suggested_commands)}
              <div class="cmd-cmds" id="cmd-commands">${_renderCommands(data.commands)}</div>
            </div>
          </section>
          <section class="cmd-panel" data-tab="commands" data-cmd-vis="audio_io" style="flex:0 0 auto;">
            ${_panelHeader('Audio I/O', 'audio_io')}
            <div class="cmd-panel-b">
              <div class="cmd-audio" id="cmd-audio" data-state="standby" role="button" tabindex="0" aria-label="Activate Jarvis voice">
                <span class="cmd-audio-dot"></span>
                <span id="cmd-audio-label">${_esc(audio.label || 'TTS Standby')}</span>
                <button type="button" class="cmd-audio-lock" id="cmd-audio-lock" title="Toggle voice lock (hold the floor)" aria-label="Toggle voice lock">Lock</button>
              </div>
              <div class="cmd-audio-hint">${_esc(audio.hint || 'Tap to arm Jarvis · Lock holds the floor · Alt+Shift+V')}</div>
            </div>
          </section>
          <section class="cmd-panel" data-tab="wire" data-cmd-vis="ai_wire">
            ${_panelHeader('AI Wire', 'ai_wire')}
            <div class="cmd-panel-b" id="cmd-wire">${_renderWire(data.wire)}</div>
          </section>
        </aside>
      </div>
      ${_renderVisSettingsDrawer()}
    </div>
  `;
}

function _tickClock() {
  const el = document.getElementById('cmd-center-clock');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const dateEl = document.getElementById('cmd-center-date');
  if (dateEl) {
    dateEl.textContent = now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase();
  }
  const syncEl = document.getElementById('cmd-sync-label');
  if (syncEl && !syncEl.matches(':hover')) {
    syncEl.textContent = _syncLabel();
    const stale = _syncedAt && (Date.now() - new Date(_syncedAt).getTime() > 60000);
    syncEl.dataset.stale = stale ? 'true' : 'false';
  }
}

function _animateHero(target) {
  const el = document.getElementById('cmd-hero-num');
  if (!el) return;
  const end = Math.max(0, Number(target) || 0);
  if (_heroAnimated && el.dataset.done === String(end)) return;
  _heroAnimated = true;
  el.dataset.done = String(end);
  const start = performance.now();
  const duration = 900;
  const step = (t) => {
    const p = Math.min(1, (t - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(end * eased).toLocaleString();
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function _mountScene() {
  const mount = document.getElementById('cmd-scene-mount');
  const stage = document.getElementById('cmd-stage');
  if (!mount) return;
  disposeCmdCenterScene();
  const inProgress = _data.counts?.handoffs_in_progress || 0;
  initCmdCenterScene(mount, {
    branchHealth: _data.branch_health || _data.status,
    inProgress,
    globeGraph: _data.globe_graph,
    onNodeClick: (action, targetId) => _runAction(action, targetId),
    onPopupOpen: (node) => _speakNodeSummary(node),
  });
  _wireAutoToggle();

  _updateCardAnchors();
  _cardAnchorObserver?.disconnect();
  if (stage) {
    _cardAnchorObserver = new ResizeObserver(() => _updateCardAnchors());
    _cardAnchorObserver.observe(stage);
  }
}

async function _speakNodeSummary(node) {
  try {
    const text = [node.label, node.summary].filter(Boolean).join(' — ').trim();
    if (!text) return;
    const mod = window.voiceRealtimeModule || (await import('./voiceRealtime.js')).default;
    mod?.speakText?.(text);
  } catch (err) {
    console.warn('scene popup speak failed', err);
  }
}

function _wireAutoToggle() {
  const chip = document.getElementById('cmd-scene-auto');
  if (!chip || chip.dataset.wired === '1') return;
  chip.dataset.wired = '1';
  const sync = () => {
    const on = isCmdCenterSceneAutoSpin?.() ?? true;
    chip.dataset.on = on ? 'true' : 'false';
  };
  chip.addEventListener('click', (ev) => {
    ev.stopPropagation();
    toggleCmdCenterSceneAutoSpin?.();
    sync();
  });
  chip.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); chip.click(); }
  });
  // Keep the chip in sync with scene-driven changes (e.g. drag pauses, dblclick resumes).
  setInterval(sync, 800);
  sync();
}

function _startSoftRefresh() {
  if (_refreshTimer) return;
  _refreshTimer = setInterval(_softRefresh, SOFT_REFRESH_MS);
}

function _stopSoftRefresh() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}

async function _softRefresh() {
  if (!_open) return;
  await _fetchData();
  if (!_open) return;

  // Soft-refresh vault brief into an armed Jarvis Realtime session.
  try {
    const voiceRealtime = window.voiceRealtimeModule;
    if (voiceRealtime?.isConnected?.() && voiceRealtime?.isJarvisMode?.()) {
      voiceRealtime.reapplyVaultBrief?.({ force: true });
    }
  } catch (_) { /* ignore */ }

  const cardsUpdated = _updateStageCardsInPlace(_data.stage_cards);
  if (!cardsUpdated) {
    _paint();
    return;
  }

  const syncEl = document.getElementById('cmd-sync-label');
  if (syncEl) syncEl.textContent = _syncLabel();

  _refreshHandoffPanelsInPlace(_data);

  updateCmdCenterScene(
    _data.branch_health || [],
    _data.counts?.handoffs_in_progress || 0,
    _data.globe_graph,
  );
  _updateCardAnchors();
}

function _pauseSceneAndClock() {
  pauseCmdCenterScene();
  _stopSoftRefresh();
  if (_clockTimer) { clearInterval(_clockTimer); _clockTimer = null; }
  _cardAnchorObserver?.disconnect();
  _cardAnchorObserver = null;
}

function _resumeSceneAndClock() {
  resumeCmdCenterScene();
  _tickClock();
  if (!_clockTimer) _clockTimer = setInterval(_tickClock, 1000);
  const mount = document.getElementById('cmd-scene-mount');
  if (mount && !mount.querySelector('canvas')) _mountScene();
  else {
    updateCmdCenterScene(
      _data.branch_health || [],
      _data.counts?.handoffs_in_progress || 0,
      _data.globe_graph,
    );
    _updateCardAnchors();
  }
  _startSoftRefresh();
}

function _ensureAgentModeForDelegate() {
  try {
    const raw = localStorage.getItem('odysseus_toggle_state');
    const state = raw ? JSON.parse(raw) : {};
    if (state.mode === 'agent') return false;
    state.mode = 'agent';
    localStorage.setItem('odysseus_toggle_state', JSON.stringify(state));
    document.getElementById('mode-agent-btn')?.click();
    return true;
  } catch (_) {
    return false;
  }
}

async function _activateVoiceDelegate() {
  const switched = _ensureAgentModeForDelegate();
  try {
    const voiceChat = window.voiceChatModule || (await import('./voiceChat.js')).default;
    const voiceRealtime = window.voiceRealtimeModule || (await import('./voiceRealtime.js')).default;

    voiceRealtime.setJarvisMode?.(true);

    if (switched) {
      voiceRealtime.reapplySessionPatch?.();
    }

    const wasActive = voiceChat.isActive?.();
    const realtimeLive = voiceChat.isRealtimeActive?.();

    if (wasActive && realtimeLive) {
      await voiceRealtime.reapplyVaultBrief?.({ force: true });
      window.uiModule?.showToast?.('Jarvis live — speak to delegate without leaving vault', 3500);
      document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
        detail: { state: voiceRealtime.isVoiceLocked?.() ? 'listening' : 'listening', label: 'Listening' },
      }));
      return;
    }

    // Ambient presence from CMD: Realtime hot mic listens immediately.
    const ok = await voiceChat.setActive(true, {
      showError: (m) => window.uiModule?.showError?.(m),
      showToast: (m) => window.uiModule?.showToast?.(m),
      autoStart: true,
    });
    if (!ok) return;

    await voiceRealtime.reapplyVaultBrief?.({ force: true });
    document.dispatchEvent(new CustomEvent('odysseus:voice-ui-state', {
      detail: { state: 'listening', label: 'Listening' },
    }));

    const msg = switched
      ? 'Jarvis on — speak naturally (agent bridge for vault work)'
      : 'Jarvis on — vault brief loaded; speak naturally';
    window.uiModule?.showToast?.(msg, 4000);
  } catch (err) {
    console.warn('[cmd-center] voice activate failed', err);
    window.uiModule?.showToast?.('Voice activation failed');
  }
}

async function _runAction(action, id) {
  if (!action) return;
  console.debug('[CMD Center]', action, id || '');

  if (action === 'refresh') {
    await _fetchData({ syncCalendar: true });
    window.dispatchEvent(new CustomEvent('calendar-refresh'));
    _paint();
    return;
  }

  if (action === 'plan_today') {
    const planId = id || _data.plan_note_id;
    if (planId && notesModule?.openNote) await notesModule.openNote(planId);
    else notesModule?.openNotes?.();
    return;
  }

  // `notes` = open the Notes surface once. `open_note` = focus a specific note.
  // Never treat a missing/category id as a note id (that close→reopen path
  // races when click handlers are stacked and spawns duplicate panes).
  if (action === 'notes') {
    notesModule?.openNotes?.();
    return;
  }
  if (action === 'open_note') {
    if (id && notesModule?.openNote) await notesModule.openNote(id);
    else notesModule?.openNotes?.();
    return;
  }
  if (action === 'open_doc') {
    if (id && documentModule?.loadDocument) await documentModule.loadDocument(id);
    else documentModule?.openLibrary?.();
    return;
  }
  if (action === 'library') {
    documentModule?.openLibrary?.();
    return;
  }
  if (action === 'tasks' || action === 'open_task') {
    tasksModule?.openTasks?.(id || undefined);
    return;
  }
  if (action === 'run_task') {
    if (!id) return;
    try {
      const res = await fetch(`${API_BASE}/api/tasks/${id}/run`, { method: 'POST', credentials: 'same-origin' });
      if (res.ok) {
        window.uiModule?.showToast?.('Agent dispatched — results land in Swarm Activity', 3500);
        setTimeout(async () => { await _fetchData(); _paint(); }, 3000);
      } else if (res.status === 409) {
        window.uiModule?.showToast?.('Agent already running');
      } else {
        window.uiModule?.showToast?.(`Dispatch failed (${res.status})`);
      }
    } catch (err) {
      console.warn('run_task failed', err);
      window.uiModule?.showToast?.('Dispatch failed');
    }
    return;
  }
  if (action === 'agent_bin') {
    agentBinModule?.openAgentBin?.();
    return;
  }
  if (action === 'email') {
    try {
      const mod = await import('./emailLibrary.js');
      mod.openEmailLibrary?.();
    } catch (err) {
      console.warn('Email open failed', err);
    }
    return;
  }
  if (action === 'research') {
    try {
      const mod = await import('./research/panel.js');
      mod.openPanel?.();
    } catch (err) {
      console.warn('Research open failed', err);
    }
    return;
  }
  if (action === 'calendar') {
    calendarModule?.openCalendar?.();
    return;
  }
  if (action === 'open_session') {
    if (id && sessionModule?.selectSession) sessionModule.selectSession(id);
    return;
  }
  if (action === 'jobs') {
    openJobAttentionPanel(_data.jobs_detail || {});
    return;
  }
  if (action === 'voice') {
    await _activateVoiceDelegate();
    return;
  }
  if (action === 'relay_watcher') {
    const cmd = '.\\scripts\\install-handoff-relay-watcher.ps1';
    try {
      await navigator.clipboard.writeText(cmd);
      window.uiModule?.showToast?.('Relay install command copied — run in PowerShell (repo root)');
    } catch (_) {
      window.uiModule?.showToast?.(cmd);
    }
    return;
  }
  // DISABLED: Docker Odysseus cannot launch the Windows WPF overlay via /api/clicky/start.
  // Use deploy/scripts/start-clicky.ps1 on the Windows host instead.
  // if (action === 'start_clicky') {
  //   window.uiModule?.showToast?.('Starting Clicky overlay…', 2500);
  //   try {
  //     const data = await launchClicky(API_BASE);
  //     clickyLaunchToast(data, (msg, ms) => window.uiModule?.showToast?.(msg, ms));
  //   } catch (err) {
  //     console.warn('start_clicky failed', err);
  //     window.uiModule?.showToast?.(`Clicky launch failed: ${err.message || err}`, 5000);
  //   }
  //   return;
  // }
}

function _setAudioUi(state, label) {
  const root = document.getElementById('cmd-audio');
  const lab = document.getElementById('cmd-audio-label');
  if (root) root.dataset.state = state || 'standby';
  if (lab) lab.textContent = label || 'TTS Standby';
}

function _bindVoiceUi() {
  if (_voiceUiHandler) return;
  _voiceUiHandler = (e) => {
    if (!_open) return;
    let state = 'standby';
    let label = 'TTS Standby';
    if (e.type === 'odysseus:voice-lock') {
      state = e.detail?.locked ? 'listening' : 'listening';
      label = e.detail?.locked ? 'Voice Locked' : 'Listening';
      _setAudioUi(state, label);
      return;
    }
    if (e.type === 'odysseus:voice-ui-state' && e.detail?.state) {
      state = e.detail.state;
      const map = {
        listening: 'Listening',
        speaking: 'Speaking',
        thinking: 'Thinking',
        standby: 'TTS Standby',
      };
      label = e.detail.label || map[state] || String(state);
      if (window.voiceRealtimeModule?.isVoiceLocked?.() && state === 'listening') {
        label = 'Voice Locked';
      }
    } else if (e.detail?.active) {
      state = 'listening';
      label = e.detail.realtime ? 'Jarvis Live' : 'Voice Armed';
    }
    _setAudioUi(state, label);
  };
  document.addEventListener('odysseus:voice-ui-state', _voiceUiHandler);
  document.addEventListener('odysseus:voice-chat-changed', _voiceUiHandler);
  document.addEventListener('odysseus:voice-lock', _voiceUiHandler);
}

function _unbindVoiceUi() {
  if (!_voiceUiHandler) return;
  document.removeEventListener('odysseus:voice-ui-state', _voiceUiHandler);
  document.removeEventListener('odysseus:voice-chat-changed', _voiceUiHandler);
  document.removeEventListener('odysseus:voice-lock', _voiceUiHandler);
  _voiceUiHandler = null;
}

let _cmdActionHandler = null;

function _bindCmdActionFromVoice() {
  if (_cmdActionHandler) return;
  _cmdActionHandler = (e) => {
    const action = e.detail?.action;
    if (!action) return;
    _runAction(action, e.detail?.id || '');
  };
  document.addEventListener('odysseus:cmd-action', _cmdActionHandler);
}

function _unbindCmdActionFromVoice() {
  if (!_cmdActionHandler) return;
  document.removeEventListener('odysseus:cmd-action', _cmdActionHandler);
  _cmdActionHandler = null;
}

let _voiceActivateRoot = null;

function _wireVoiceActivate(root) {
  if (_voiceActivateRoot === root) return;
  _voiceActivateRoot = root;
  root.addEventListener('click', (e) => {
    const lockBtn = e.target.closest('#cmd-audio-lock');
    if (lockBtn && root.contains(lockBtn)) {
      e.preventDefault();
      e.stopPropagation();
      const rt = window.voiceRealtimeModule;
      if (!rt?.isConnected?.()) {
        _activateVoiceDelegate();
        return;
      }
      const locked = rt.toggleVoiceLock?.();
      window.uiModule?.showToast?.(
        locked ? 'Voice lock on — finish your thought' : 'Voice lock off — ambient listen',
        2500,
      );
      return;
    }
    const audio = e.target.closest('#cmd-audio');
    if (!audio || !root.contains(audio)) return;
    e.preventDefault();
    _activateVoiceDelegate();
  });
  root.addEventListener('keydown', (e) => {
    if (e.target?.id !== 'cmd-audio') return;
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    _activateVoiceDelegate();
  });
}

function _wireClicks(root) {
  // Pane element survives _paint()'s innerHTML swaps — guard so each refresh
  // does not stack another delegated click listener (N paints ⇒ N opens).
  if (!root || root.dataset.cmdClicksWired === '1') return;
  root.dataset.cmdClicksWired = '1';
  root.addEventListener('click', (e) => {
    const target = e.target.closest('[data-action]');
    if (!target || !root.contains(target)) return;
    e.preventDefault();
    _runAction(target.dataset.action, target.dataset.id || '');
  });
}

function _wireChrome(root) {
  document.getElementById('cmd-center-minimize')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    _closePanel('down');
  });
}

function _wireSwipe(pane) {
  const dismiss = () => _closePanel('down');
  wireSwipeDismiss(pane.querySelector('.cmd-mobile-grabber'), pane, dismiss);
  wireSwipeDismiss(pane.querySelector('.cmd-topbar'), pane, dismiss);
}

function _isMobileViewport() {
  return window.matchMedia?.('(max-width: 720px)')?.matches ?? false;
}

function _setMobileTab(name) {
  _mobileTab = name;
  const root = document.getElementById('cmd-center-root');
  if (root) root.dataset.mobileTab = name;
  document.querySelectorAll('#cmd-tabs .cmd-tab').forEach((b) => {
    b.setAttribute('aria-pressed', b.dataset.tab === name ? 'true' : 'false');
  });
  if (root) _updateMobileEmptyHints(root);
  if (_isMobileViewport()) {
    if (name === 'hud') {
      resumeCmdCenterScene();
      requestAnimationFrame(() => { _updateCardAnchors(); });
    } else {
      pauseCmdCenterScene();
    }
  } else {
    resumeCmdCenterScene();
  }
}

function _wireTabs(root) {
  const tabs = root.querySelector('#cmd-tabs');
  if (!tabs || tabs.dataset.wired === '1') return;
  tabs.dataset.wired = '1';
  tabs.addEventListener('click', (e) => {
    const btn = e.target.closest('.cmd-tab');
    if (!btn) return;
    e.preventDefault();
    _setMobileTab(btn.dataset.tab);
  });
}

function _wireResizeReconcile() {
  if (_resizeHandler) return;
  _resizeHandler = () => {
    if (!_open) return;
    if (!_isMobileViewport() || _mobileTab === 'hud') resumeCmdCenterScene();
    else pauseCmdCenterScene();
    requestAnimationFrame(_updateCardAnchors);
  };
  window.addEventListener('resize', _resizeHandler);
}

function _paint() {
  const pane = document.getElementById(PANE_ID);
  if (!pane) return;
  _visSettingsWired = false;
  _infoPopoverWired = false;
  pane.innerHTML = _buildHTML(_data);
  const root = document.getElementById('cmd-center-root');
  _wireClicks(pane);
  _wireVoiceActivate(pane);
  _wireChrome(pane);
  _wireSwipe(pane);
  if (root) {
    _wireVisSettings(root);
    _wireInfoPopovers(root);
    _applyVisibilityPrefs(root);
  }
  _wireTabs(pane);
  _tickClock();
  _animateHero(_data.hero?.value || 0);
  _mountScene();
  _setMobileTab(_mobileTab);
}

function _forceCloseCmdCenter() {
  _open = false;
  _pauseSceneAndClock();
  disposeCmdCenterScene();
  _voiceActivateRoot = null;
  _unbindVoiceUi();
  _visSettingsWired = false;
  _infoPopoverWired = false;
  if (_resizeHandler) { window.removeEventListener('resize', _resizeHandler); _resizeHandler = null; }
  document.body.classList.remove('cmd-center-view');
  document.getElementById('tool-cmd-center-btn')?.classList.remove('active');
  document.getElementById('rail-cmd-center')?.classList.remove('active');
  try { Modals.unregister(PANEL_ID); } catch {}
  try { document.getElementById(PANE_ID)?.remove(); } catch {}
  try { window._restoreSidebarIfRouteCollapsed?.(); } catch {}
}

function _ensureCmdCenterChipRegistered() {
  if (Modals.isRegistered(PANEL_ID)) return;
  Modals.register(PANEL_ID, {
    railBtnId: 'rail-cmd-center',
    sidebarBtnId: 'tool-cmd-center-btn',
    restoreFn: () => { openCmdCenter(); },
    closeFn: () => { _forceCloseCmdCenter(); },
  });
}

function _closePanel(direction) {
  if (!_open) return;
  _open = false;
  _pauseSceneAndClock();
  _unbindVoiceUi();
  // Keep odysseus:cmd-action listener + Realtime session alive across
  // minimize so Jarvis stays armed while the vault chip remains.

  const minimize = direction === 'down';
  if (minimize) {
    _ensureCmdCenterChipRegistered();
    try {
      const live = window.voiceChatModule?.isRealtimeActive?.();
      if (live) {
        window.uiModule?.showToast?.('Jarvis stays armed while vault is minimized', 2500);
      }
    } catch (_) { /* ignore */ }
  } else if (Modals.isRegistered(PANEL_ID)) {
    try { Modals.unregister(PANEL_ID); } catch {}
  }

  document.body.classList.remove('cmd-center-view');
  document.getElementById('tool-cmd-center-btn')?.classList.remove('active');
  document.getElementById('rail-cmd-center')?.classList.remove('active');
  try { window._restoreSidebarIfRouteCollapsed?.(); } catch {}

  disposeCmdCenterScene();
  _voiceActivateRoot = null;
  if (_resizeHandler) { window.removeEventListener('resize', _resizeHandler); _resizeHandler = null; }
  try { document.getElementById(PANE_ID)?.remove(); } catch {}

  if (minimize) {
    try { Modals.minimize(PANEL_ID); } catch {}
  }
}

export async function openCmdCenter() {
  _ensureStyles();
  if (Modals.isMinimized(PANEL_ID)) {
    Modals.restore(PANEL_ID);
    return;
  }
  if (_open) return;

  const container = document.getElementById('chat-container');
  if (!container) return;

  _open = true;
  _heroAnimated = false;
  _mobileTab = 'hud';

  document.body.classList.add('cmd-center-view');
  collapseSidebarForMobileSheet();

  document.getElementById('tool-cmd-center-btn')?.classList.add('active');
  document.getElementById('rail-cmd-center')?.classList.add('active');

  document.getElementById(PANE_ID)?.remove();
  const pane = document.createElement('div');
  pane.id = PANE_ID;
  pane.className = 'cmd-center-pane';
  container.insertAdjacentElement('afterend', pane);

  if (window.innerWidth <= 768) {
    pane.style.animation = 'sheet-enter 0.25s cubic-bezier(0.2, 0.8, 0.2, 1) both';
    pane.style.transformOrigin = 'bottom center';
  }

  pane.innerHTML = _buildHTML(_data);
  _wireClicks(pane);
  _wireVoiceActivate(pane);
  _wireChrome(pane);
  _wireSwipe(pane);
  _wireTabs(pane);
  _setMobileTab(_mobileTab);

  _tickClock();
  _clockTimer = setInterval(_tickClock, 1000);
  _bindVoiceUi();
  _bindCmdActionFromVoice();
  _wireResizeReconcile();

  Modals.register(PANEL_ID, {
    railBtnId: 'rail-cmd-center',
    sidebarBtnId: 'tool-cmd-center-btn',
    restoreFn: () => { openCmdCenter(); },
    closeFn: () => { _forceCloseCmdCenter(); },
  });

  await _fetchData({ syncCalendar: true });
  if (_open) {
    _paint();
    _startSoftRefresh();
  }
}

export function minimizeCmdCenter() {
  _closePanel('down');
}

export function closeCmdCenter() {
  if (!_open && !Modals.isMinimized(PANEL_ID)) return;
  if (Modals.isRegistered(PANEL_ID)) Modals.close(PANEL_ID);
  else _forceCloseCmdCenter();
}

export function isCmdCenterOpen() {
  if (Modals.isMinimized(PANEL_ID)) return false;
  return _open;
}

export function toggleCmdCenter() {
  if (isCmdCenterOpen()) minimizeCmdCenter();
  else openCmdCenter();
}

const cmdCenterModule = {
  openCmdCenter,
  closeCmdCenter,
  minimizeCmdCenter,
  isCmdCenterOpen,
  toggleCmdCenter,
  activateVoiceDelegate: _activateVoiceDelegate,
};

export default cmdCenterModule;
window.cmdCenterModule = cmdCenterModule;
window._cmdActivateVoiceDelegate = _activateVoiceDelegate;

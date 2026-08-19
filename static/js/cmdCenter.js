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
  highlightNodes,
  clearHighlights,
} from './cmdCenterScene.js';
import { openJobAttentionPanel } from './cmdCenterJobs.js';
import { wireSwipeDismiss, collapseSidebarForMobileSheet } from './panelSheet.js';
import {
  initCmdCenterAudio,
  destroyCmdCenterAudio,
  runBrief,
  stopBrief,
  setVoiceEnabled,
  earconDone,
  earconAttn,
  earconMsg,
  earconError,
} from './cmdCenterAudio.js';
import {
  startCmdCenterLive,
  stopCmdCenterLive,
  renderLiveBanner,
  CMD_LIVE_BANNER_CSS,
} from './cmdCenterLive.js';
import { openDirectiveTriage, closeDirectiveTriage, isDirectiveTriageOpen } from './cmdCenterDirective.js';
import { createSpaceHoldTracker } from './cmdCenterHotkeys.js';
import {
  captureCmdEditableFocus,
  cmdEditableOwnsFocus,
  restoreCmdEditableFocus,
} from './cmdCenterFocus.js';
import { mdToHtml } from './markdown.js';
// DISABLED with /clicky: Docker cannot spawn Windows WPF via /api/clicky/start.
// import { launchClicky, clickyLaunchToast } from './clickyLaunch.js';

const API_BASE = window.location.origin;
const PANEL_ID = 'cmd-center-panel';
const PANE_ID = 'cmd-center-pane';
const WIRE_EXPANDED_KEY = 'odysseus-cmd-wire-expanded';
const RAILS_COLLAPSED_KEY = 'odysseus-cmd-rails-collapsed';
const VOICE_MUTE_KEY = 'odysseus-cmd-voice-mute';

const DATA = {
  title: 'V.A.U.L.T.',
  subtitle: 'Odysseus Command Center',
  status: [],
  branch_health: [],
  vitals: [],
  priority_queue: [],
  directives: [],
  documents: [],
  notes_preview: [],
  comms_preview: [],
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
  attention_stack: [],
  ceo_brief: { status: 'missing', content: '', title: 'CEO Brief' },
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
let _cardAnchorObserver = null;
let _resizeHandler = null;
let _globalHotkeysWired = false;
let _spaceHold = null;
let _visSettingsWired = false;
let _infoPopoverWired = false;
let _syncInFlight = false;

const VIS_STORAGE_KEY = 'odysseus-cmd-center-visibility';
/** @deprecated superseded by CMD_VIEW_KEY — read once for one-time migration only. */
const DOMAIN_TAB_KEY = 'odysseus-cmd-domain-tab';
/** One shared { view, domainFilter } preference — same schema on desktop and mobile. */
const CMD_VIEW_KEY = 'odysseus-cmd-view';
const PROD_ORBITAL_STATUS_KEY = 'odysseus-cmd-prod-orbital-status-v1';
const PROD_ORBITAL_DONE_KEY = 'odysseus-cmd-prod-orbital-done-v1';
/** Ids already POSTed in this page session for localStorage→server status backfill. */
const _prodStatusBackfilled = new Set();
const PROD_TASK_STATUSES = new Set(['queued', 'in_progress', 'blocked', 'done']);
const DOMAIN_TABS = ['CORE', 'MEM', 'PROD', 'COMMS', 'AGENCY', 'RELAY', 'MYCELIA'];
const MOBILE_TABS = ['hud', 'queue', 'commands', 'wire'];

/**
 * Orbital-style composition map — each tab mounts a dedicated panel set.
 * Keys resolve to render helpers in _renderPanelById.
 */
const TAB_LAYOUT = {
  CORE: {
    left: ['vitals', 'priority_queue', 'swarm_activity', 'documents'],
    right: ['command_deck', 'audio_io', 'ai_wire'],
  },
  MEM: {
    left: ['notes_rail'],
    right: ['mem_focus', 'documents', 'ai_wire'],
  },
  PROD: {
    left: ['task_board'],
    right: ['directive', 'ai_wire'],
  },
  COMMS: {
    left: ['comms_inbox'],
    right: ['comms_focus', 'ai_wire'],
  },
  AGENCY: {
    left: ['agency_board'],
    right: ['agency_focus', 'audio_io'],
  },
  RELAY: {
    left: ['relay_board'],
    right: ['relay_stats'],
  },
  MYCELIA: {
    left: ['mycelia_activity', 'mycelia_signals'],
    right: ['mycelia_fruit', 'mycelia_stats', 'command_deck'],
  },
};

/** Branch keys (lowercase) for queue/wire filters. null = all. */
const DOMAIN_TAB_BRANCHES = {
  CORE: null,
  MEM: ['mem', 'intel'],
  PROD: ['prod'],
  COMMS: ['comms'],
  AGENCY: ['agency'],
  RELAY: ['relay'],
  MYCELIA: ['mycelia'],
};

/** Command deck groups per tab when showing command_deck. null = all. */
const DOMAIN_TAB_CMD_GROUPS = {
  CORE: null,
  MEM: ['Foundation', 'Intel'],
  PROD: ['Foundation'],
  COMMS: ['Intel'],
  AGENCY: ['Agency'],
  RELAY: ['Agency', 'Ops'],
  MYCELIA: ['Mycelia'],
};

/** Mobile status pill branch id → domain tab (voice ignored). */
const PILL_BRANCH_TO_TAB = {
  core: 'CORE',
  mem: 'MEM',
  intel: 'MEM',
  prod: 'PROD',
  comms: 'COMMS',
  agency: 'AGENCY',
  relay: 'RELAY',
  mycelia: 'MYCELIA',
};

/** branch_health ids per domain tab — for attention dots. */
const DOMAIN_TAB_BRANCH_IDS = {
  CORE: ['core'],
  MEM: ['mem', 'intel'],
  PROD: ['prod'],
  COMMS: ['comms'],
  AGENCY: ['agency'],
  RELAY: ['relay'],
  MYCELIA: ['mycelia'],
};

/**
 * Reconciled nav state: one { view, domainFilter } pair shared by desktop
 * and mobile. `view` is the canonical HUD/Queue/Commands/Wire grouping;
 * `domainFilter` is the CORE/MEM/PROD/... lens applied within it. Falls back
 * to a one-time read of the legacy domain-tab-only key so an existing
 * preference (e.g. "I always land on RELAY") carries forward.
 */
function _loadViewState() {
  try {
    const raw = localStorage.getItem(CMD_VIEW_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        view: MOBILE_TABS.includes(parsed?.view) ? parsed.view : 'hud',
        domainFilter: DOMAIN_TABS.includes(parsed?.domainFilter) ? parsed.domainFilter : 'CORE',
      };
    }
    const legacy = localStorage.getItem(DOMAIN_TAB_KEY);
    if (legacy && DOMAIN_TABS.includes(legacy)) {
      return { view: 'hud', domainFilter: legacy };
    }
  } catch { /* ignore */ }
  return { view: 'hud', domainFilter: 'CORE' };
}

function _persistViewState(view, domainFilter) {
  try {
    localStorage.setItem(CMD_VIEW_KEY, JSON.stringify({ view, domainFilter }));
  } catch { /* ignore */ }
}

const _initialViewState = _loadViewState();
let _domainTab = _initialViewState.domainFilter;
let _mobileTab = _initialViewState.view;
let _commsInboxFilter = 'unread';

const COMMS_INBOX_FILTERS = [
  ['unread', 'Unread'],
  ['triage', 'Needs triage'],
  ['all', 'All'],
];

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
  notes_rail: {
    label: 'Notes Rail',
    goal: 'Browse and open recent notes without leaving the vault (MEM tab).',
    provenance: 'notes_preview[] — newest non-archived notes from build_cmd_center.',
    action: 'Click a card to open the note; Open Notes jumps to the Notes panel.',
  },
  task_board: {
    label: 'Task Board',
    goal: 'PROD orbital Tasks — OPEN / BLOCKED / DONE with priority accent + status cycle.',
    provenance: 'priority_queue / directives (prod) mapped to orbital workflow; status overrides in localStorage.',
    action: 'Click a card to open; START / DONE / REOPEN cycles status; All Tasks opens Tasks panel.',
  },
  mem_focus: {
    label: 'MEM Focus',
    goal: 'Memory / intel ritual controls for the MEM tab.',
    provenance: 'Static guidance + ceo_brief / notes actions.',
    action: 'Compile Brief or open Notes.',
  },
  directive: {
    label: 'Directive',
    goal: 'PROD focus summary — what this branch is driving toward.',
    provenance: 'hero + prod queue counts when on PROD tab.',
    action: 'Informational; use left board or Command Deck to act.',
  },
  agency_board: {
    label: 'Agency Board',
    goal: 'Job pipeline cards — ready to apply and needs review.',
    provenance: 'jobs_detail + non-swarm agent_activity.',
    action: 'Click a job row or Open Jobs to open the job attention panel.',
  },
  agency_focus: {
    label: 'Agency Focus',
    goal: 'AM Report ritual — review jobs and agency commands.',
    provenance: 'Agency command group + jobs_detail headline.',
    action: 'Open Jobs / AM Report or use Audio I/O.',
  },
  relay_board: {
    label: 'Relay Board',
    goal: 'Handoff queue waiting for operator attention.',
    provenance: 'priority_queue filtered branch=relay + relay branch_health.',
    action: 'Click a handoff row or open Agent Bin.',
  },
  relay_stats: {
    label: 'Relay Stats',
    goal: 'Relay branch health and install/agent controls.',
    provenance: 'branch_health relay + Ops/Agency relay commands.',
    action: 'Agent Bin or Install Relay watcher script.',
  },
  comms_inbox: {
    label: 'Comms Inbox',
    goal: 'Recent inbox rows with optional urgency triage overlay.',
    provenance: 'comms_preview from live INBOX list + email_urgency_state when scanned.',
    action: 'Click a message row or Open Inbox.',
  },
  comms_focus: {
    label: 'Comms Focus',
    goal: 'Inbox brief and email surface shortcuts.',
    provenance: 'branch_health comms + Intel inbox commands.',
    action: 'Open Inbox or Inbox Brief.',
  },
  mycelia_activity: {
    label: 'Mycelia Activity',
    goal: 'Swarm agent runs, pulse excerpts, and graph node snapshot.',
    provenance: 'agent_activity (swarm) + mycelia_feed.pulse + globe_graph nodes summary.',
    action: 'Click a swarm line to open the task.',
  },
  mycelia_signals: {
    label: 'Swarm Signals',
    goal: 'Cross-guild SIGNAL lines from the blackboard harvest.',
    provenance: 'mycelia_feed.signals parsed from blackboard + spill notes.',
    action: 'Click a signal to open its source note or doc.',
  },
  mycelia_fruit: {
    label: 'Fruit Ledger',
    goal: 'Pending fruit at the sporulation gate and recent wins.',
    provenance: 'mycelia_feed.fruit from Fruit Ledger doc.',
    action: 'Open Fruit Ledger doc from Mycelia deck.',
  },
  mycelia_stats: {
    label: 'Graph Stats',
    goal: 'Globe graph nodes/edges/by-type breakdown.',
    provenance: 'globe_graph meta + node kinds.',
    action: 'Informational; dispatch from Mycelia deck.',
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
    if (mins < 1) return 'just now';
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
  if (!rel || rel === 'just now') return 'synced just now';
  return `synced ${rel} ago`;
}

function _isSyncStale() {
  return Boolean(_fetchError || (_syncedAt && (Date.now() - new Date(_syncedAt).getTime() > 60000)));
}

function _paintSyncChrome({ text, stale } = {}) {
  const label = document.getElementById('cmd-sync-label');
  const btn = document.getElementById('cmd-vault-sync');
  const nextStale = stale ?? _isSyncStale();
  const nextText = text ?? _syncLabel();
  if (label) {
    if (!label.matches(':hover')) label.textContent = nextText;
    label.dataset.stale = nextStale ? 'true' : 'false';
  }
  if (btn) btn.dataset.stale = nextStale ? 'true' : 'false';
}

function _setHeaderSyncBusy(busy) {
  const btn = document.getElementById('cmd-vault-sync');
  if (!btn) return;
  btn.dataset.busy = busy ? 'true' : 'false';
  btn.setAttribute('aria-busy', busy ? 'true' : 'false');
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
  let style = document.getElementById('cmd-center-styles');
  if (!style) {
    style = document.createElement('style');
    style.id = 'cmd-center-styles';
    document.head.appendChild(style);
  }
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
.cmd-topbar-spacer { flex: 1; min-width: 8px; }
.cmd-status-row { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; justify-content: center; }
.cmd-pill {
  position: relative;
  border: 1px solid rgba(166,226,46,0.28); background: rgba(166,226,46,0.04); color: #a6e22e;
  font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase;
  padding: 4px 8px; border-radius: 2px; cursor: pointer;
}
.cmd-pill:hover { background: rgba(166,226,46,0.12); box-shadow: 0 0 8px rgba(166,226,46,0.25); }
.cmd-pill[data-state="online"], .cmd-pill[data-state="alive"] { box-shadow: 0 0 8px rgba(166,226,46,0.25); }
.cmd-pill[data-state="busy"], .cmd-pill[data-state="attention"] { color: #7fff00; border-color: rgba(255,107,107,0.55); animation: cmdPillPulse 1.4s ease-in-out infinite; }
.cmd-pill[data-state="armed"] { color: #ffb347; border-color: rgba(255,179,71,0.55); }
.cmd-pill[data-state="idle"] { opacity: 0.55; }
.cmd-pill-dot {
  position: absolute; top: -3px; right: -3px;
  width: 7px; height: 7px; border-radius: 50%;
  background: #ff5c49; box-shadow: 0 0 6px rgba(255,92,73,0.8);
  pointer-events: none;
}
.cmd-pill-dot.amber {
  background: #ffb347; box-shadow: 0 0 6px rgba(255,179,71,0.75);
}
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

.cmd-domain-tabs {
  display: flex; gap: 4px; flex-shrink: 1; min-width: 0;
  overflow-x: auto; scrollbar-width: none; margin-left: 4px;
}
.cmd-domain-tabs::-webkit-scrollbar { display: none; }
.cmd-domain-tab {
  position: relative;
  flex-shrink: 0;
  background: transparent;
  border: 1px solid #1f2630;
  color: #7a8694;
  padding: 6px 10px;
  font: inherit;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 150ms;
}
.cmd-domain-tab[aria-pressed="true"] {
  background: rgba(255,154,60,0.12);
  border-color: #ff9a3c;
  color: #ff9a3c;
}
.cmd-domain-tab:hover {
  color: #c8d0d8;
  border-color: #3a4550;
}
.cmd-domain-tab:focus { outline: none; }
.cmd-domain-tab:focus-visible {
  outline: 1px solid #4dd8e6;
  outline-offset: 1px;
}
.cmd-domain-tab-dot {
  position: absolute; top: 3px; right: 3px;
  width: 6px; height: 6px; border-radius: 50%;
  background: #ff5c49; box-shadow: 0 0 5px rgba(255,92,73,0.85);
  pointer-events: none;
}
.cmd-domain-tab-dot.amber {
  background: #ffb347; box-shadow: 0 0 5px rgba(255,179,71,0.75);
}
/* Mobile stand-in for .cmd-domain-tabs — a lens picker, not a second tab strip. */
.cmd-domain-select { display: none; }
.cmd-branch-focus {
  border: 1px solid rgba(255,154,60,0.28);
  background: rgba(255,154,60,0.06);
  padding: 8px 10px;
  font-size: 10px;
  letter-spacing: 0.08em;
}
.cmd-branch-focus-label {
  font-size: 8px; letter-spacing: 0.2em; color: #ff9a3c; text-transform: uppercase;
}
.cmd-branch-focus-summary { margin-top: 4px; color: #c8d0d8; opacity: 0.85; }
#cmd-left-panels, #cmd-right-panels {
  display: flex; flex-direction: column; gap: 10px; min-height: 0; flex: 1;
  overflow-y: auto;
}

.cmd-notes-tools { display: flex; gap: 6px; margin-bottom: 6px; }
.cmd-notes-search {
  flex: 1; min-width: 0;
  background: rgba(10,14,20,0.6); border: 1px solid rgba(166,226,46,0.22);
  color: #a6e22e; padding: 6px 8px; font: inherit; font-size: 10px; letter-spacing: 0.08em;
  outline: none;
}
.cmd-notes-search:focus { border-color: #4dd8e6; }
.cmd-notes-open, .cmd-board-open-tasks {
  border: 1px solid rgba(166,226,46,0.35); background: transparent; color: #a6e22e;
  font: inherit; font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
  padding: 6px 8px; cursor: pointer; white-space: nowrap;
}
.cmd-notes-open:hover, .cmd-board-open-tasks:hover { color: #7fff00; border-color: #7fff00; }
.cmd-notes-meta { font-size: 9px; opacity: 0.55; letter-spacing: 0.12em; margin-bottom: 8px; }
.cmd-notes-list { display: flex; flex-direction: column; gap: 6px; }
.cmd-note-card {
  background: rgba(10,14,20,0.45); border: 1px solid rgba(166,226,46,0.16);
  border-left: 3px solid #4dd8e6; padding: 8px 10px; cursor: pointer;
}
.cmd-note-card[data-pinned="1"] { border-left-color: #ff9a3c; }
.cmd-note-card:hover { border-color: rgba(166,226,46,0.4); color: #7fff00; }
.cmd-note-card-h { display: flex; align-items: center; gap: 6px; }
.cmd-note-pin { color: #ff9a3c; font-size: 11px; flex-shrink: 0; }
.cmd-note-title { flex: 1; min-width: 0; font-size: 11px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmd-note-ago { font-size: 8px; opacity: 0.5; flex-shrink: 0; }
.cmd-note-preview { font-size: 10px; opacity: 0.65; margin-top: 4px; line-height: 1.35; }
.cmd-note-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
.cmd-note-tag {
  font-size: 8px; letter-spacing: 0.1em; text-transform: uppercase;
  border: 1px solid rgba(166,226,46,0.25); padding: 2px 5px; opacity: 0.75;
}

.cmd-board-counts {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  font-size: 9px; letter-spacing: 0.12em; margin-bottom: 10px;
}
.cmd-board-count.overdue { color: #ff8a8a; }
.cmd-board-count.due { color: #ffb347; }
.cmd-board-count.open { color: #ff9a3c; }
.cmd-board-count.blocked { color: #ff4a4a; }
.cmd-board-count.done { color: #4dd8e6; }
.cmd-board-open-tasks { margin-left: auto; }
.cmd-board-section { margin-bottom: 10px; }
.cmd-board-label {
  font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; opacity: 0.65;
  display: flex; justify-content: space-between; margin-bottom: 4px;
}
.cmd-board-foot { font-size: 8px; opacity: 0.45; letter-spacing: 0.12em; margin-top: 4px; }

/* Orbital PROD TaskBoard — scoped so AGENCY/RELAY boards keep vault chrome */
#cmd-task-board .cmd-board-counts {
  margin-top: 6px; margin-bottom: 0; color: #7a8694;
}
#cmd-task-board .cmd-board-section { margin-bottom: 4px; }
#cmd-task-board .cmd-board-label {
  display: flex; align-items: center; gap: 6px; justify-content: flex-start;
  margin: 4px 0; font-size: 9px; color: #5a6470; letter-spacing: 0.25em;
  text-transform: uppercase; opacity: 1;
}
#cmd-task-board .cmd-board-label span { color: #ff9a3c; letter-spacing: 0; }
#cmd-task-board .cmd-board-label::after {
  content: ""; flex: 1; height: 1px; background: #1a2030;
}
#cmd-task-board .cmd-board-list { display: flex; flex-direction: column; gap: 6px; }

.cmd-prod-add {
  width: 100%; margin-top: 8px; box-sizing: border-box;
  background: rgba(10,14,20,0.6); border: 1px solid #1a2030; color: #c8d0d8;
  padding: 6px 8px; font: inherit; font-size: 10px; outline: none;
}
.cmd-prod-add:focus { border-color: #2a3040; }
.cmd-prod-add::placeholder { color: #5a6470; }
.cmd-prod-card {
  background: rgba(10,14,20,0.55); border: 1px solid #1a2030;
  border-left-width: 3px; border-left-style: solid;
  padding: 8px 10px; cursor: pointer;
}
.cmd-prod-card:hover { border-color: #2a3040; }
.cmd-prod-card-h { display: flex; align-items: center; gap: 6px; }
.cmd-prod-title {
  flex: 1; min-width: 0; font-size: 11px; color: #c8d0d8; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cmd-prod-status { font-size: 8px; letter-spacing: 0.1em; flex-shrink: 0; }
.cmd-prod-desc {
  font-size: 10px; color: #7a8694; margin-top: 4px; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.cmd-prod-related {
  font-size: 9px; color: #5a6470; margin-top: 3px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cmd-prod-foot { display: flex; gap: 4px; margin-top: 6px; align-items: center; }
.cmd-prod-tag {
  font-size: 8px; letter-spacing: 0.15em; padding: 1px 5px; text-transform: uppercase;
  background: rgba(77,216,230,0.08); border: 1px solid #2a3040; color: #7a8694;
}
.cmd-prod-due { font-size: 9px; color: #5a6470; }
.cmd-prod-move {
  background: transparent; border: 1px solid #1f2630; color: #7a8694;
  font: inherit; font-size: 9px; padding: 2px 6px; cursor: pointer;
}
.cmd-prod-move:hover { color: #c8d0d8; border-color: #2a3040; }

.cmd-mem-focus-copy { font-size: 10px; line-height: 1.45; opacity: 0.7; margin-bottom: 10px; }
.cmd-mem-brief {
  width: 100%; margin-bottom: 8px;
  background: rgba(255,154,60,0.1); border: 1px solid #ff9a3c; color: #ff9a3c;
  font: inherit; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase;
  padding: 8px; cursor: pointer;
}
.cmd-mem-brief:hover { background: rgba(255,154,60,0.18); }
.cmd-mem-brief-kicker {
  font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
  color: #ff9a3c; margin-bottom: 8px;
}
.cmd-mem-brief-md {
  font-size: 11px; line-height: 1.5; color: #c8d0d8;
  max-height: min(52vh, 420px); overflow: auto;
  padding: 8px 10px; margin-bottom: 10px;
  background: rgba(0,0,0,0.25); border: 1px solid #1f2630;
}
.cmd-mem-brief-md h1, .cmd-mem-brief-md h2, .cmd-mem-brief-md h3 {
  font-size: 12px; letter-spacing: 0.06em; margin: 10px 0 6px; color: #e7edf5;
}
.cmd-mem-brief-md h1 { font-size: 13px; margin-top: 0; }
.cmd-mem-brief-md p, .cmd-mem-brief-md li { margin: 0 0 6px; }
.cmd-mem-brief-md pre, .cmd-mem-brief-md code {
  font-size: 10px; white-space: pre-wrap; word-break: break-word;
}
.cmd-mem-brief-md ul, .cmd-mem-brief-md ol { padding-left: 1.2em; margin: 0 0 8px; }
.cmd-mem-focus-actions { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; }
.cmd-directive-mark {
  font-size: 22px; color: #ff9a3c; font-weight: 600; letter-spacing: 0.12em; line-height: 1.1;
}
.cmd-directive-blurb { font-size: 10px; line-height: 1.45; opacity: 0.75; margin-top: 8px; }
.cmd-directive-meta { font-size: 9px; opacity: 0.55; margin: 8px 0 10px; letter-spacing: 0.08em; }

/* ── PLAN TODAY triage sheet ── */
.cmd-today-backdrop {
  position: absolute; inset: 0; z-index: 40;
  background: rgba(0,0,0,0.55);
  display: flex; align-items: stretch; justify-content: flex-end;
  animation: cmd-today-fade 160ms ease both;
}
@keyframes cmd-today-fade { from { opacity: 0; } to { opacity: 1; } }
.cmd-today-sheet {
  width: min(420px, 100%); height: 100%;
  background: #0a0e14; border-left: 1px solid #2a3040;
  display: flex; flex-direction: column; min-height: 0;
  box-shadow: -12px 0 40px rgba(0,0,0,0.45);
  animation: cmd-today-slide 200ms cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
@keyframes cmd-today-slide { from { transform: translateX(24px); opacity: 0.6; } to { transform: none; opacity: 1; } }
.cmd-today-head {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 14px 14px 10px; border-bottom: 1px solid #1a2030; flex-shrink: 0;
}
.cmd-today-head-text { flex: 1; min-width: 0; }
.cmd-today-kicker {
  font-size: 9px; letter-spacing: 0.22em; text-transform: uppercase; color: #ff9a3c;
}
.cmd-today-title {
  font-size: 16px; font-weight: 600; color: #c8d0d8; letter-spacing: 0.04em; margin-top: 2px;
}
.cmd-today-summary {
  font-size: 10px; color: #7a8694; margin-top: 4px; line-height: 1.4;
}
.cmd-today-close {
  background: transparent; border: 1px solid #1f2630; color: #7a8694;
  width: 28px; height: 28px; cursor: pointer; font: inherit; font-size: 14px;
  flex-shrink: 0;
}
.cmd-today-close:hover { color: #c8d0d8; border-color: #2a3040; }
.cmd-today-body {
  flex: 1; min-height: 0; overflow: auto; padding: 10px 12px 16px;
  display: flex; flex-direction: column; gap: 8px;
}
.cmd-today-empty {
  font-size: 11px; color: #5a6470; padding: 24px 8px; text-align: center; line-height: 1.5;
}
.cmd-today-row {
  background: rgba(10,14,20,0.7); border: 1px solid #1a2030;
  border-left: 3px solid #4dd8e6; padding: 10px 10px 8px;
}
.cmd-today-row[data-band="stale"] { border-left-color: #ff5c49; }
.cmd-today-row[data-band="overdue"] { border-left-color: #ff4a4a; }
.cmd-today-row[data-band="due"] { border-left-color: #ff9a3c; }
.cmd-today-row[data-band="fat"] { border-left-color: #ffd966; }
.cmd-today-row-h { display: flex; align-items: flex-start; gap: 6px; }
.cmd-today-row-title {
  flex: 1; min-width: 0; font-size: 12px; font-weight: 600; color: #c8d0d8;
  line-height: 1.35; cursor: pointer;
}
.cmd-today-row-title:hover { color: #7fff00; }
.cmd-today-band {
  font-size: 8px; letter-spacing: 0.14em; text-transform: uppercase;
  padding: 2px 5px; border: 1px solid #2a3040; color: #7a8694; flex-shrink: 0;
}
.cmd-today-row[data-band="stale"] .cmd-today-band { color: #ff5c49; border-color: rgba(255,92,73,0.4); }
.cmd-today-row[data-band="overdue"] .cmd-today-band { color: #ff4a4a; border-color: rgba(255,74,74,0.4); }
.cmd-today-row[data-band="due"] .cmd-today-band { color: #ff9a3c; border-color: rgba(255,154,60,0.4); }
.cmd-today-row[data-band="fat"] .cmd-today-band { color: #ffd966; border-color: rgba(255,217,102,0.4); }
.cmd-today-meta {
  font-size: 10px; color: #7a8694; margin-top: 4px; line-height: 1.4;
}
.cmd-today-preview {
  font-size: 10px; color: #5a6470; margin-top: 4px; line-height: 1.35;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.cmd-today-actions {
  display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px;
}
.cmd-today-btn {
  background: transparent; border: 1px solid #1f2630; color: #7a8694;
  font: inherit; font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 4px 8px; cursor: pointer;
}
.cmd-today-btn:hover { color: #c8d0d8; border-color: #2a3040; }
.cmd-today-btn[data-plan-act="archive"]:hover { color: #b48a4a; border-color: rgba(180,138,74,0.55); }
.cmd-today-btn[data-plan-act="delegate"]:hover { color: #7fff00; border-color: rgba(127,255,0,0.4); }
.cmd-today-btn[data-plan-act="block"]:hover { color: #4dd8e6; border-color: rgba(77,216,230,0.45); }
.cmd-today-delegate {
  display: none; flex-wrap: wrap; gap: 4px; width: 100%; margin-top: 2px;
}
.cmd-today-delegate.is-open { display: flex; }
.cmd-today-foot {
  flex-shrink: 0; padding: 10px 12px; border-top: 1px solid #1a2030;
  display: flex; gap: 6px;
}
.cmd-today-foot .cmd-mem-brief { margin: 0; flex: 1; }

.cmd-job-card, .cmd-comms-card {
  background: rgba(10,14,20,0.45); border: 1px solid rgba(166,226,46,0.16);
  border-left: 3px solid #7fff00; padding: 8px 10px; cursor: pointer;
}
.cmd-job-card[data-tier="review"] { border-left-color: #ffb347; }
.cmd-comms-card[data-urgent="1"] { border-left-color: #ff5c49; }
.cmd-job-card:hover, .cmd-comms-card:hover { border-color: rgba(166,226,46,0.4); color: #7fff00; }
.cmd-job-card-h, .cmd-comms-card-h { display: flex; align-items: center; gap: 6px; }
.cmd-job-title, .cmd-comms-subject { flex: 1; min-width: 0; font-size: 11px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmd-job-meta, .cmd-comms-from { font-size: 9px; opacity: 0.6; margin-top: 3px; }
.cmd-comms-filters { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.cmd-comms-filter {
  font-size: 9px; padding: 3px 7px; border-radius: 999px; border: 1px solid rgba(166,226,46,0.25);
  background: transparent; color: inherit; opacity: 0.75; cursor: pointer;
}
.cmd-comms-filter.is-active { opacity: 1; border-color: rgba(166,226,46,0.65); color: #a6e22e; }
.cmd-comms-card[data-unread="0"] { opacity: 0.82; }
.cmd-relay-stat-row { display: flex; justify-content: space-between; font-size: 10px; padding: 4px 0; border-bottom: 1px solid rgba(166,226,46,0.08); }
.cmd-relay-bucket-label { font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.65; margin: 2px 0 4px; }
.cmd-graph-stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 10px; }
.cmd-graph-stat {
  border: 1px solid rgba(166,226,46,0.2); padding: 8px; text-align: center;
  font-size: 16px; font-weight: 700; color: #4dd8e6;
}
.cmd-graph-stat span { display: block; font-size: 8px; letter-spacing: 0.14em; opacity: 0.55; font-weight: 400; margin-top: 2px; }
.cmd-graph-kind { font-size: 9px; opacity: 0.7; padding: 2px 0; display: flex; justify-content: space-between; }


.cmd-grid {
  position: relative; z-index: 6;
  display: flex; align-items: stretch;
  gap: 12px; padding: 12px; min-height: 0; flex: 1;
}
.cmd-rail[data-cmd-rail="left"],
.cmd-rail[data-cmd-rail="right"] {
  position: relative;
  flex: 0 1 280px; min-width: 240px; max-width: 320px;
  transition: flex-basis 0.2s ease, min-width 0.2s ease, max-width 0.2s ease, opacity 0.15s ease;
}
.cmd-rail[data-rail-hidden="true"] { display: none !important; }
.cmd-rail[data-rail-collapsed="true"] {
  flex: 0 0 22px; min-width: 22px; max-width: 22px; overflow: hidden;
}
.cmd-rail[data-rail-collapsed="true"] > .cmd-panel,
.cmd-rail[data-rail-collapsed="true"] > #cmd-left-panels,
.cmd-rail[data-rail-collapsed="true"] > #cmd-right-panels { display: none !important; }
.cmd-rail-toggle {
  position: absolute; top: 8px; z-index: 3;
  width: 18px; height: 28px; padding: 0;
  border: 1px solid rgba(166,226,46,0.28); background: rgba(5,10,5,0.92); color: #a6e22e;
  font: 600 11px/1 'JetBrains Mono', monospace; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  opacity: 0.55;
}
.cmd-rail[data-cmd-rail="left"]:not([data-rail-collapsed="true"]) .cmd-rail-toggle { right: -10px; }
.cmd-rail[data-cmd-rail="right"]:not([data-rail-collapsed="true"]) .cmd-rail-toggle { left: -10px; }
.cmd-rail-toggle:hover { opacity: 1; color: #7fff00; box-shadow: 0 0 8px rgba(166,226,46,0.25); }
.cmd-rail[data-rail-collapsed="true"] .cmd-rail-toggle {
  position: relative; top: auto; left: auto; right: auto;
  width: 100%; height: 100%; min-height: 64px; opacity: 0.85;
  writing-mode: vertical-rl; letter-spacing: 0.18em; font-size: 9px;
}
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
.cmd-rail[data-cmd-rail="left"]:not([data-rail-collapsed="true"]) .cmd-panel-h { padding-right: 30px; }
.cmd-rail[data-cmd-rail="right"]:not([data-rail-collapsed="true"]) .cmd-panel-h { padding-left: 30px; }
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
  display: flex; gap: 8px; align-items: flex-start; padding: 7px 0;
  border-bottom: 1px solid rgba(166,226,46,0.07); cursor: pointer; font-size: 11px;
}
.cmd-dir-item:hover, .cmd-doc-item:hover { color: #7fff00; text-shadow: 0 0 8px rgba(127,255,0,0.35); }
.cmd-dir-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; background: #a6e22e; }
.cmd-dir-dot[data-branch="relay"] { background: #ff6b6b; box-shadow: 0 0 6px rgba(255,107,107,0.6); }
.cmd-dir-dot[data-branch="agency"] { background: #7fff00; }
.cmd-dir-dot[data-branch="mycelia"] { background: #c678dd; box-shadow: 0 0 6px rgba(198,120,221,0.55); }
.cmd-dir-dot[data-status="overdue"] { background: #ff5c49; box-shadow: 0 0 7px rgba(255,92,73,0.65); }
.cmd-dir-dot[data-status="due"] { background: #ffb347; box-shadow: 0 0 6px rgba(255,179,71,0.5); }
.cmd-dir-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.cmd-dir-title, .cmd-doc-title {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 11px; line-height: 1.4;
}
.cmd-dir-meta, .cmd-doc-meta {
  font-size: 8px; opacity: 0.65; letter-spacing: 0.08em;
  display: flex; gap: 7px; align-items: center; flex-wrap: wrap;
}
.cmd-chip {
  font-size: 7px; letter-spacing: 0.1em; padding: 2px 6px; border: 1px solid;
  text-transform: uppercase; flex-shrink: 0;
}
.cmd-chip.red { color: #ff5c49; border-color: #7a2a22; background: rgba(255,92,73,0.08); }
.cmd-chip.amber { color: #ffb347; border-color: #7a5a22; background: rgba(255,179,71,0.08); }
.cmd-chip.ok { color: #a6e22e; border-color: rgba(166,226,46,0.35); background: rgba(166,226,46,0.06); }

.cmd-swarm { display: flex; flex-direction: column; gap: 2px; }
.cmd-swarm-line {
  display: flex; gap: 8px; align-items: baseline; padding: 5px 0;
  border-bottom: 1px solid rgba(166,226,46,0.06); cursor: pointer; font-size: 10px;
}
.cmd-swarm-line:hover { color: #7fff00; }
.cmd-swarm-st { color: #a6e22e; min-width: 10px; }
.cmd-swarm-st.idle { color: rgba(166,226,46,0.4); }
.cmd-swarm-st.err { color: #ff5c49; }
.cmd-swarm-w { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cmd-swarm-ago { font-size: 8px; opacity: 0.45; flex-shrink: 0; margin-left: auto; }
.cmd-raw-toggle {
  margin-top: 8px; background: none; border: 1px solid rgba(166,226,46,0.22);
  color: rgba(166,226,46,0.55); font: 600 8px/1 'JetBrains Mono', monospace;
  letter-spacing: 0.16em; padding: 5px 9px; cursor: pointer; text-transform: uppercase;
}
.cmd-raw-toggle:hover { color: #7fff00; border-color: rgba(166,226,46,0.45); }
.cmd-raw-log {
  display: none; margin-top: 8px; font-size: 8px; line-height: 1.55;
  color: rgba(166,226,46,0.45); max-height: 96px; overflow: auto; white-space: pre-wrap;
}
.cmd-raw-log.show { display: block; }

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
/* Passive: this item's "next action" already lives on the hero (or another
 * primary slot) — still navigable, just not competing for attention. */
.cmd-float-card--passive { opacity: 0.55; box-shadow: none; border-style: dashed; }
.cmd-float-card--passive:hover { opacity: 0.85; box-shadow: 0 0 10px rgba(166,226,46,0.18); }
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
.cmd-glance {
  position: relative; z-index: 3; display: flex; flex-wrap: wrap; gap: 8px;
  padding: 10px 14px 0; pointer-events: none;
}
.cmd-glance-chip {
  pointer-events: auto;
  font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase;
  border: 1px solid rgba(166,226,46,0.28); background: rgba(5,10,5,0.72);
  color: #a6e22e; padding: 5px 9px; backdrop-filter: blur(2px);
}
.cmd-glance-chip strong { font-weight: 700; color: #7fff00; margin-left: 6px; letter-spacing: 0.08em; }
.cmd-glance-chip[data-attn="true"] { color: #ff8a7a; border-color: rgba(255,92,73,0.45); }
.cmd-glance-chip[data-attn="true"] strong { color: #ff5c49; }
.cmd-hero-label { font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.7; }
.cmd-hero-title { font-size: 12px; margin-top: 4px; opacity: 0.9; }
.cmd-hero-value { font-size: 34px; font-weight: 700; letter-spacing: 0.08em; margin-top: 6px; text-shadow: 0 0 18px rgba(166,226,46,0.45); }
.cmd-hero[data-attn="overdue"] .cmd-hero-value { color: #ff5c49; text-shadow: 0 0 26px rgba(255,92,73,0.45); }
.cmd-hero-unit { font-size: 12px; letter-spacing: 0.18em; margin-left: 8px; opacity: 0.7; }
.cmd-hero-explain { font-size: 10px; opacity: 0.65; margin-top: 6px; line-height: 1.4; max-width: 520px; }
.cmd-hero-vel { font-size: 10px; opacity: 0.55; margin-top: 4px; letter-spacing: 0.1em; }
.cmd-hero-cta {
  display: inline-block; margin-top: 8px; font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
  border: 1px solid rgba(166,226,46,0.35); padding: 5px 10px; opacity: 0.85;
}
.cmd-quick-read {
  margin: 8px 0 4px; padding: 8px 10px; max-width: 520px;
  border: 1px solid rgba(166,226,46,0.18); background: rgba(5,10,5,0.55);
}
.cmd-quick-read-label { font-size: 8px; letter-spacing: 0.24em; text-transform: uppercase; opacity: 0.55; margin-bottom: 6px; }
.cmd-quick-read-list { margin: 0; padding-left: 16px; list-style: disc; }
.cmd-quick-read-item { font-size: 10px; line-height: 1.45; opacity: 0.88; margin-bottom: 3px; }
.cmd-quick-read-item[data-kind="signal"] { color: #ffb347; }
.cmd-quick-read-item[data-kind="health"] { color: #ff8a7a; }
.cmd-myc-health {
  display: flex; gap: 8px; align-items: baseline; font-size: 9px; letter-spacing: 0.1em;
  padding: 6px 0 8px; border-bottom: 1px solid rgba(166,226,46,0.12); margin-bottom: 6px;
}
.cmd-myc-health[data-attn="true"] .cmd-myc-health-text { color: #ff8a7a; }
.cmd-myc-health-label { opacity: 0.55; text-transform: uppercase; }
.cmd-myc-signal-row, .cmd-myc-pulse-row, .cmd-myc-fruit-row {
  padding: 6px 0; border-bottom: 1px solid rgba(166,226,46,0.07); cursor: pointer; font-size: 10px;
}
.cmd-myc-signal-row:hover, .cmd-myc-pulse-row:hover { color: #7fff00; }
.cmd-myc-signal-human { border-left: 2px solid #ffb347; padding-left: 8px; }
.cmd-myc-signal-meta, .cmd-myc-pulse-agent { font-size: 8px; opacity: 0.6; letter-spacing: 0.08em; text-transform: uppercase; }
.cmd-myc-signal-text, .cmd-myc-pulse-text { margin-top: 3px; line-height: 1.4; }
.cmd-myc-fruit-row { display: flex; justify-content: space-between; gap: 8px; cursor: default; }
.cmd-board-label { font-size: 8px; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.5; margin-bottom: 4px; }

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
.cmd-wire-toggle {
  margin-top: 6px; align-self: flex-start;
  border: 1px solid rgba(166,226,46,0.28); background: transparent; color: rgba(166,226,46,0.7);
  font: 600 8px/1 'JetBrains Mono', monospace; letter-spacing: 0.14em; text-transform: uppercase;
  padding: 5px 9px; cursor: pointer;
}
.cmd-wire-toggle:hover { color: #7fff00; border-color: rgba(166,226,46,0.5); }

.cmd-now-bar {
  position: relative; z-index: 8; flex: 0 0 auto;
  min-height: 64px; max-height: 76px;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px;
  border-top: 1px solid rgba(166,226,46,0.28);
  background: rgba(4,9,5,0.96);
  box-shadow: 0 -8px 24px rgba(0,0,0,0.45);
}
.cmd-brief-btn {
  flex-shrink: 0;
  border: 1px solid rgba(166,226,46,0.65); background: rgba(166,226,46,0.08); color: #a6e22e;
  font: 700 11px/1 'JetBrains Mono', monospace; letter-spacing: 0.22em; text-transform: uppercase;
  padding: 12px 14px; cursor: pointer; min-width: 108px;
}
.cmd-brief-btn:hover { color: #7fff00; border-color: #7fff00; box-shadow: 0 0 14px rgba(166,226,46,0.35); background: rgba(166,226,46,0.14); }
.cmd-now-text {
  flex: 1; min-width: 0; font-size: 11px; letter-spacing: 0.1em;
  opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cmd-now-actions { display: flex; gap: 8px; flex-shrink: 0; }
.cmd-voice-mute, .cmd-earcon-demo {
  border: 1px solid rgba(166,226,46,0.28); background: transparent; color: #a6e22e;
  font: 600 9px/1 'JetBrains Mono', monospace; letter-spacing: 0.14em; text-transform: uppercase;
  padding: 8px 10px; cursor: pointer;
}
.cmd-voice-mute[aria-pressed="true"] { color: #ffb347; border-color: rgba(255,179,71,0.55); }
.cmd-voice-mute:hover, .cmd-earcon-demo:hover { color: #7fff00; border-color: rgba(166,226,46,0.5); }

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
  .cmd-topbar-spacer { display: none; }

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
  .cmd-rail-toggle { display: none; }
  .cmd-rail[data-rail-collapsed="true"] {
    flex: unset; min-width: 0; max-width: none; overflow: visible;
  }
  .cmd-rail[data-rail-collapsed="true"] > .cmd-panel,
  .cmd-rail[data-rail-collapsed="true"] > #cmd-left-panels,
  .cmd-rail[data-rail-collapsed="true"] > #cmd-right-panels { display: flex !important; }
  .cmd-now-bar { min-height: 56px; max-height: none; flex-wrap: wrap; gap: 8px; padding: 8px 10px; }
  .cmd-brief-btn { padding: 10px 12px; font-size: 10px; }

  .cmd-center-root[data-mobile-tab="hud"] .cmd-grid [data-tab]:not([data-tab="hud"]) { display: none; }
  .cmd-center-root[data-mobile-tab="queue"] .cmd-grid [data-tab]:not([data-tab="queue"]) { display: none; }
  .cmd-center-root[data-mobile-tab="commands"] .cmd-grid [data-tab]:not([data-tab="commands"]) { display: none; }
  .cmd-center-root[data-mobile-tab="wire"] .cmd-grid [data-tab]:not([data-tab="wire"]) { display: none; }
  .cmd-center-root:not([data-mobile-tab="hud"]) .cmd-status-strip { display: none; }
  /* One tab strip on mobile: .cmd-tabs. The CORE/MEM/PROD/... domain lens
   * collapses to a select so it never reads as a second row of nav tabs,
   * and stays reachable from every view (not just HUD). */
  .cmd-domain-tabs { display: none; }
  .cmd-domain-select {
    display: block; flex: 0 1 124px; min-width: 0;
    background: rgba(5,10,5,0.85); border: 1px solid #1f2630; color: #ff9a3c;
    font: inherit; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 8px 20px 8px 6px; cursor: pointer; -webkit-appearance: none; appearance: none;
    background-image: linear-gradient(45deg, transparent 50%, #7a8694 50%), linear-gradient(135deg, #7a8694 50%, transparent 50%);
    background-position: calc(100% - 12px) calc(50% + 1px), calc(100% - 8px) calc(50% + 1px);
    background-size: 4px 4px, 4px 4px;
    background-repeat: no-repeat;
  }
  .cmd-domain-select:focus-visible { outline: 1px solid #4dd8e6; outline-offset: 1px; }
  .cmd-domain-select option { background: #050a05; color: #c8d0d8; letter-spacing: normal; }

  /* PROD orbital task cards: stack full width, keep actions thumb-sized. */
  #cmd-task-board .cmd-prod-card { padding: 10px 12px; }
  #cmd-task-board .cmd-prod-title { white-space: normal; }
  #cmd-task-board .cmd-prod-move { font-size: 10px; padding: 8px 12px; }
  #cmd-task-board .cmd-prod-add { padding: 10px 8px; font-size: 11px; }
  #cmd-task-board .cmd-board-open-tasks { padding: 8px 10px; }

  .cmd-float-card { display: none !important; }
  .cmd-stage { min-height: 58vh; }
  .cmd-hero-value { font-size: 28px; }
  .cmd-topbar { padding: 10px 12px; gap: 8px; }
  /* Yield to the domain select before the brand starts clipping. */
  .cmd-brand { flex: 0 0 auto; max-width: 46%; overflow: hidden; }
  .cmd-brand-title { font-size: 15px; letter-spacing: 0.22em; white-space: nowrap; }
  .cmd-brand-sub { display: none; }
  .cmd-clock { font-size: 16px; }
  .cmd-clock-wrap { min-width: 80px; }
  .cmd-sync-btn, .cmd-settings-btn { width: 28px; height: 28px; }
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

.cmd-settings-btn,
.cmd-sync-btn {
  position: relative; z-index: 7; flex-shrink: 0;
  width: 32px; height: 32px; border-radius: 6px;
  border: 1px solid rgba(166,226,46,0.28); background: rgba(5,10,5,0.85);
  color: #a6e22e; cursor: pointer; display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
}
.cmd-settings-btn:hover,
.cmd-sync-btn:hover { box-shadow: 0 0 10px rgba(127,255,0,0.35); color: #7fff00; }
.cmd-sync-btn[data-stale="true"] { color: #ffb347; border-color: rgba(255,179,71,0.55); }
.cmd-sync-btn[data-busy="true"] { color: #7fff00; }
.cmd-sync-btn[data-busy="true"] svg { animation: cmdSyncSpin 0.75s linear infinite; }
@keyframes cmdSyncSpin { to { transform: rotate(360deg); } }

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
` + CMD_LIVE_BANNER_CSS;
}

function _mapNoteRowToPreview(n) {
  const body = String(n.content || n.body || '').trim();
  const preview = body ? body.split('\n')[0].slice(0, 140) : '';
  const tags = [];
  if (n.label) tags.push(n.label);
  if (Array.isArray(n.tags)) tags.push(...n.tags.filter(Boolean));
  const title = String(n.title || '').trim() || 'Untitled note';
  return {
    id: n.id,
    title,
    preview,
    pinned: !!n.pinned,
    tags: tags.slice(0, 4),
    updated_at: n.updated_at,
    action: 'open_note',
    target_id: n.id,
  };
}

/** Backfill MEM rail when cmd-center predates notes_preview in the payload. */
async function _hydrateNotesPreviewIfMissing() {
  if (Array.isArray(_data.notes_preview) && _data.notes_preview.length > 0) return;
  const noteCount = Number(_data.counts?.notes ?? 0);
  if (noteCount <= 0) return;
  try {
    const res = await fetch(`${API_BASE}/api/notes`, { credentials: 'same-origin' });
    if (!res.ok) return;
    const body = await res.json();
    const rows = (body.notes || body || []).filter((n) => !n.archived);
    rows.sort((a, b) => {
      const ta = Date.parse(a.updated_at || '') || 0;
      const tb = Date.parse(b.updated_at || '') || 0;
      return tb - ta;
    });
    _data.notes_preview = rows.slice(0, 16).map(_mapNoteRowToPreview);
  } catch (err) {
    console.warn('[cmd-center] notes preview hydrate failed', err);
  }
}

/**
 * @param {{ syncCalendar?: boolean, live?: boolean }} [opts] `live: true` is
 *   the poll path — sends `since_hash` (short-circuits to `{unchanged:true}`
 *   when nothing changed) and `include_globe=0` (globe_graph is the most
 *   expensive step and changes far less often than notes/tasks; the initial
 *   open fetch still requests it).
 * @returns {Promise<boolean>} true when the server reported `unchanged`
 *   (caller should skip re-rendering and only refresh the sync label).
 */
async function _fetchData({ syncCalendar = false, live = false } = {}) {
  try {
    const params = new URLSearchParams();
    if (syncCalendar) params.set('sync_calendar', '1');
    if (live) {
      params.set('include_globe', '0');
      if (_data?.payload_hash) params.set('since_hash', _data.payload_hash);
    }
    const qs = params.toString() ? `?${params.toString()}` : '';
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
    if (payload && payload.unchanged) {
      _syncedAt = payload.synced_at || new Date().toISOString();
      _fetchError = null;
      return true;
    }
    // include_globe=0 polls omit globe_graph entirely — keep rendering the
    // last-known one instead of losing it (see vault-live-sync-efficiency).
    const prevGlobeGraph = _data?.globe_graph;
    _data = { ...DATA, ...payload };
    if (!('globe_graph' in payload) && prevGlobeGraph) _data.globe_graph = prevGlobeGraph;
    await _hydrateNotesPreviewIfMissing();
    _syncedAt = payload.synced_at || new Date().toISOString();
    _fetchError = null;
    return false;
  } catch (err) {
    console.warn('CMD Center fetch failed', err);
    if (!_fetchError) _fetchError = `Sync failed (${err.message || 'network'}) — click Vault Sync.`;
    if (!(_data.vitals && _data.vitals.length)) _data = { ...DATA };
    return false;
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

function _chipClass(status) {
  if (status === 'overdue') return 'red';
  if (status === 'due') return 'amber';
  return 'ok';
}

function _renderDirectives(list) {
  if (!list?.length) return '<div class="cmd-empty">Clear deck — nothing queued</div>';
  return list.map((d) => {
    const status = d.status || '';
    const chip = d.due_label || '';
    const branch = (d.branch || '').toUpperCase();
    const chipHtml = chip
      ? `<span class="cmd-chip ${_chipClass(status)}">${_esc(chip)}</span>`
      : '';
    const branchHtml = branch ? `<span>${_esc(branch)}</span>` : '';
    const related = (d.related_to || [])
      .map((x) => `${x.kind}:${x.id}`)
      .filter(Boolean)
      .slice(0, 2)
      .join(' · ');
    const relatedHtml = related
      ? `<span class="cmd-dir-related" title="${_esc(related)}">from ${_esc(related)}</span>`
      : '';
    // Fall back to meta only when no chip/branch — never show raw ISO due strings.
    const metaFallback = (!chip && !branch && d.meta && !/\d{4}-\d{2}-\d{2}T/.test(d.meta))
      ? `<span>${_esc(d.meta)}</span>`
      : '';
    return `
    <div class="cmd-dir-item" data-action="${_esc(d.action || '')}" data-id="${_esc(d.target_id || d.id || '')}">
      <span class="cmd-dir-dot" data-branch="${_esc(d.branch || '')}" data-status="${_esc(status)}"></span>
      <div class="cmd-dir-body">
        <div class="cmd-dir-title" title="${_esc(d.title)}">${_esc(d.title)}</div>
        <div class="cmd-dir-meta">${chipHtml}${branchHtml}${relatedHtml}${metaFallback}</div>
      </div>
    </div>`;
  }).join('');
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
  return (list || []).map((s) => {
    const st = String(s.state || '').toLowerCase();
    const count = Number(s.count) || 0;
    const needsDot = st === 'attention' || st === 'busy' || st === 'armed' || count > 0;
    const dotClass = (st === 'busy' || st === 'attention') ? '' : ' amber';
    const dot = needsDot ? `<span class="cmd-pill-dot${dotClass}" aria-hidden="true"></span>` : '';
    return `<button type="button" class="cmd-pill" data-state="${_esc(s.state)}" data-action="${_esc(s.action || '')}" data-branch-id="${_esc(s.id || '')}" title="${_esc(s.summary || s.label)}">${dot}${_esc(s.label)}</button>`;
  }).join('');
}

/** Prefer status[]; fill missing count from branch_health only for non-calm states. */
function _statusForRender(data) {
  const list = data?.status || [];
  const byId = Object.create(null);
  for (const b of (data?.branch_health || [])) {
    if (b?.id) byId[b.id] = b;
  }
  return list.map((s) => {
    const bh = byId[s.id] || {};
    const state = String(s.state || bh.state || '').toLowerCase();
    const hot = state === 'attention' || state === 'busy' || state === 'armed' || state === 'alive';
    const count = s.count != null ? s.count : (hot ? (bh.count ?? 0) : 0);
    return {
      ...s,
      count,
      state: s.state || bh.state || '',
      summary: s.summary || bh.summary || '',
    };
  });
}

function _persistDomainTab(tab) {
  _persistViewState(_mobileTab, tab);
}

function _filterByBranch(list, tab) {
  const branches = DOMAIN_TAB_BRANCHES[tab];
  if (!branches) return list || [];
  return (list || []).filter((item) => branches.includes(String(item.branch || '').toLowerCase()));
}

function _filterCommandsForTab(list, tab) {
  const groups = DOMAIN_TAB_CMD_GROUPS[tab];
  if (!groups) return list || [];
  return (list || []).filter((c) => groups.includes(c.group || ''));
}

/** Option text mirrors the tab attention dot as a trailing marker. */
function _domainOptionLabel(tab, data) {
  return _domainTabAttention(data, tab).show ? `${tab} •` : tab;
}

function _renderDomainTabs(data = _data) {
  return `<nav class="cmd-domain-tabs" id="cmd-domain-tabs" aria-label="Vault domain tabs">
    ${DOMAIN_TABS.map((tab) => {
      const attn = _domainTabAttention(data, tab);
      const dotClass = attn.hot ? '' : ' amber';
      const dot = attn.show
        ? `<span class="cmd-domain-tab-dot${dotClass}" aria-hidden="true"></span>`
        : '';
      return `
      <button type="button" class="cmd-domain-tab" data-domain-tab="${tab}"
        aria-pressed="${_domainTab === tab ? 'true' : 'false'}">${tab}${dot}</button>`;
    }).join('')}
  </nav>
  <select class="cmd-domain-select" id="cmd-domain-select" aria-label="Vault domain filter">
    ${DOMAIN_TABS.map((tab) => `<option value="${tab}"${_domainTab === tab ? ' selected' : ''}>${_esc(_domainOptionLabel(tab, data))}</option>`).join('')}
  </select>`;
}

function _updateDomainTabDots(root, data = _data) {
  if (!root) return;
  root.querySelectorAll('#cmd-domain-tabs .cmd-domain-tab').forEach((btn) => {
    const tab = btn.dataset.domainTab;
    const attn = _domainTabAttention(data, tab);
    let dot = btn.querySelector('.cmd-domain-tab-dot');
    if (!attn.show) {
      dot?.remove();
      return;
    }
    if (!dot) {
      dot = document.createElement('span');
      dot.className = 'cmd-domain-tab-dot';
      dot.setAttribute('aria-hidden', 'true');
      btn.appendChild(dot);
    }
    dot.classList.toggle('amber', !attn.hot);
  });
  root.querySelectorAll('#cmd-domain-select option').forEach((opt) => {
    opt.textContent = _domainOptionLabel(opt.value, data);
  });
}

function _renderBranchFocus(data, tab) {
  if (tab === 'CORE') return '';
  const want = String(tab).toLowerCase();
  const health = data.branch_health || [];
  let bh = health.find((b) => b.id === want);
  if (!bh && tab === 'MEM') bh = health.find((b) => b.id === 'intel') || health.find((b) => b.id === 'mem');
  if (!bh) {
    return `<div class="cmd-branch-focus" id="cmd-branch-focus">
      <div class="cmd-branch-focus-label">${_esc(tab)}</div>
      <div class="cmd-branch-focus-summary">No live branch signal</div>
    </div>`;
  }
  return `<div class="cmd-branch-focus" id="cmd-branch-focus" data-action="${_esc(bh.action || '')}">
    <div class="cmd-branch-focus-label">${_esc(tab)} · ${_esc((bh.state || '').toUpperCase())}</div>
    <div class="cmd-branch-focus-summary">${_esc(bh.summary || bh.label || '')}${bh.count ? ` · ${bh.count}` : ''}</div>
  </div>`;
}

function _renderNotesRail(data) {
  const notes = data.notes_preview || [];
  const cards = notes.length
    ? notes.map((n) => {
      const search = `${n.title || ''} ${n.preview || ''} ${(n.tags || []).join(' ')}`.toLowerCase();
      const rel = _formatRelative(n.updated_at);
      const tags = (n.tags || []).map((t) => `<span class="cmd-note-tag">${_esc(t)}</span>`).join('');
      return `
      <div class="cmd-note-card" data-action="${_esc(n.action || 'open_note')}" data-id="${_esc(n.target_id || n.id || '')}"
        data-search="${_esc(search)}" data-pinned="${n.pinned ? '1' : '0'}">
        <div class="cmd-note-card-h">
          <span class="cmd-note-pin" aria-hidden="true">${n.pinned ? '★' : '☆'}</span>
          <span class="cmd-note-title" title="${_esc(n.title)}">${_esc(n.title)}</span>
          <span class="cmd-note-ago">${_esc(rel || '')}</span>
        </div>
        ${n.preview ? `<div class="cmd-note-preview">${_esc(n.preview)}</div>` : ''}
        ${tags ? `<div class="cmd-note-tags">${tags}</div>` : ''}
      </div>`;
    }).join('')
    : '<div class="cmd-empty">No notes yet</div>';
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="notes_rail">
    ${_panelHeader('Notes', 'notes_rail')}
    <div class="cmd-panel-b" id="cmd-notes-rail">
      <div class="cmd-notes-tools">
        <input type="search" id="cmd-notes-search" class="cmd-notes-search" placeholder="search…" autocomplete="off" />
        <button type="button" class="cmd-notes-open" data-action="notes">Open Notes →</button>
      </div>
      <div class="cmd-notes-meta">${notes.length} recent</div>
      <div class="cmd-notes-list" id="cmd-notes-list">${cards}</div>
    </div>
  </section>`;
}

/** Orbital PROD task colors — priority accent / status label (vault-orbital handoff). */
function _priorityColor(p) {
  return p === 'critical' ? '#ff4a4a' : p === 'high' ? '#ff9a3c' : p === 'medium' ? '#ffd966' : '#4dd8e6';
}
function _statusColor(s) {
  return s === 'done' ? '#4dd8e6' : s === 'in_progress' ? '#ff9a3c' : s === 'blocked' ? '#ff4a4a' : '#7a8694';
}

function _loadProdOrbitalStatusMap() {
  try {
    const raw = JSON.parse(localStorage.getItem(PROD_ORBITAL_STATUS_KEY) || '{}');
    return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  } catch { return {}; }
}
function _saveProdOrbitalStatusMap(map) {
  try { localStorage.setItem(PROD_ORBITAL_STATUS_KEY, JSON.stringify(map)); } catch { /* ignore */ }
}
function _loadProdOrbitalDoneSnap() {
  try {
    const raw = JSON.parse(localStorage.getItem(PROD_ORBITAL_DONE_KEY) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch { return []; }
}
function _saveProdOrbitalDoneSnap(list) {
  try { localStorage.setItem(PROD_ORBITAL_DONE_KEY, JSON.stringify((list || []).slice(0, 12))); } catch { /* ignore */ }
}

/**
 * Map Odysseus directive due-state → orbital workflow status when no server
 * ``task_status`` is set yet.
 * Odysseus: overdue | due | calm  →  orbital: blocked | in_progress | queued
 * Server ``notes.task_status`` is source of truth (design D3); localStorage is
 * only used once for backfill when the server field is null.
 */
function _deriveOrbitalStatus(item) {
  const st = String(item?.status || '').toLowerCase();
  if (st === 'overdue') return 'blocked';
  if (st === 'due') return 'in_progress';
  return 'queued';
}

function _orbitalPriority(item) {
  const u = Number(item?.urgency) || 0;
  const st = String(item?.status || '').toLowerCase();
  if (st === 'overdue' || u >= 85) return 'critical';
  if (st === 'due' || u >= 80) return 'high';
  if (u >= 70) return 'medium';
  return 'low';
}

function _scheduleProdStatusBackfill(id, status) {
  const key = String(id || '');
  if (!key || !PROD_TASK_STATUSES.has(status) || _prodStatusBackfilled.has(key)) return;
  _prodStatusBackfilled.add(key);
  fetch(`${API_BASE}/api/notes/${encodeURIComponent(key)}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_status: status }),
  }).then((res) => {
    if (!res.ok) {
      _prodStatusBackfilled.delete(key);
      return;
    }
    // Drop this id from the legacy map so we don't keep re-reading it.
    const map = _loadProdOrbitalStatusMap();
    if (map[key]) {
      delete map[key];
      _saveProdOrbitalStatusMap(map);
    }
  }).catch(() => {
    _prodStatusBackfilled.delete(key);
  });
}

function _resolveOrbitalStatus(item, overrides) {
  const id = String(item?.id || item?.target_id || '');
  const server = String(item?.task_status || '').toLowerCase();
  if (PROD_TASK_STATUSES.has(server)) return server;
  const ov = overrides?.[id];
  if (PROD_TASK_STATUSES.has(ov)) {
    _scheduleProdStatusBackfill(id, ov);
    return ov;
  }
  return _deriveOrbitalStatus(item);
}

function _formatOrbitalDue(dueAt) {
  if (!dueAt) return '';
  const d = new Date(dueAt);
  if (Number.isNaN(d.getTime())) return '';
  return `due ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
}

function _formatRelatedToChip(relatedTo) {
  const list = Array.isArray(relatedTo) ? relatedTo : [];
  const first = list.find((r) => r && (r.kind || r.id));
  if (!first) return '';
  const kind = String(first.kind || 'item').toLowerCase();
  const rid = String(first.id || '');
  const short = rid.length > 10 ? `${rid.slice(0, 8)}…` : rid;
  return `← ${kind}${short ? ` · ${short}` : ''}`;
}

function _normalizeProdOrbitalItem(item, overrides) {
  const id = String(item.id || item.target_id || '');
  return {
    id,
    kind: item.kind || 'note',
    title: item.title || 'Untitled',
    description: item.meta || item.subtitle || '',
    priority: _orbitalPriority(item),
    status: _resolveOrbitalStatus(item, overrides),
    task_status: item.task_status || null,
    task_status_at: item.task_status_at || null,
    related_to: Array.isArray(item.related_to) ? item.related_to : [],
    due: item.due_at || null,
    action: item.action || 'open_note',
    target_id: item.target_id || id,
    urgency: item.urgency,
  };
}

function _bucketProdQueue(data) {
  const items = _filterByBranch(data.directives || data.priority_queue, 'PROD');
  const overrides = _loadProdOrbitalStatusMap();
  const live = items.map((i) => _normalizeProdOrbitalItem(i, overrides));
  const liveIds = new Set(live.map((t) => t.id));

  const open = live.filter((t) => t.status === 'queued' || t.status === 'in_progress');
  const blocked = live.filter((t) => t.status === 'blocked');
  let done = live.filter((t) => t.status === 'done');

  const snaps = _loadProdOrbitalDoneSnap()
    .filter((s) => s && s.id && !liveIds.has(String(s.id)))
    .map((s) => ({
      id: String(s.id),
      kind: s.kind || 'note',
      title: s.title || 'Untitled',
      description: s.description || '',
      priority: s.priority || 'low',
      status: 'done',
      due: s.due || null,
      action: s.action || 'open_note',
      target_id: s.target_id || String(s.id),
    }));
  done = [...done, ...snaps];

  return { open, blocked, done, total: live.length, all: live };
}

function _orbitalActionLabel(status) {
  if (status === 'queued') return 'START';
  if (status === 'in_progress') return 'DONE';
  return 'REOPEN';
}

function _orbitalNextStatus(status) {
  if (status === 'queued') return 'in_progress';
  if (status === 'in_progress') return 'done';
  return 'queued';
}

function _renderProdTaskCard(task) {
  const statusLabel = String(task.status || 'queued').toUpperCase().replace('_', ' ');
  const due = _formatOrbitalDue(task.due);
  const next = _orbitalNextStatus(task.status);
  const actionLabel = _orbitalActionLabel(task.status);
  const related = _formatRelatedToChip(task.related_to);
  return `
    <div class="cmd-prod-card" style="border-left-color:${_priorityColor(task.priority)}"
      data-action="${_esc(task.action || 'open_note')}" data-id="${_esc(task.target_id || task.id)}">
      <div class="cmd-prod-card-h">
        <span class="cmd-prod-title" title="${_esc(task.title)}">${_esc(task.title)}</span>
        <span class="cmd-prod-status" style="color:${_statusColor(task.status)}">${_esc(statusLabel)}</span>
      </div>
      ${task.description ? `<div class="cmd-prod-desc">${_esc(task.description)}</div>` : ''}
      ${related ? `<div class="cmd-prod-related" title="${_esc(related)}">${_esc(related)}</div>` : ''}
      <div class="cmd-prod-foot">
        <span class="cmd-prod-tag">${_esc(task.priority || 'low')}</span>
        ${due ? `<span class="cmd-prod-due">${_esc(due)}</span>` : '<span class="cmd-prod-due"></span>'}
        <div style="flex:1"></div>
        <button type="button" class="cmd-prod-move" data-prod-move="${_esc(next)}" data-id="${_esc(task.id)}"
          data-kind="${_esc(task.kind || '')}">→ ${_esc(actionLabel)}</button>
      </div>
    </div>`;
}

function _renderTaskBoard(data) {
  const { open, blocked, done, total } = _bucketProdQueue(data);
  const section = (label, list, empty, cap) => {
    const shown = typeof cap === 'number' ? list.slice(0, cap) : list;
    return `
    <div class="cmd-board-section">
      <div class="cmd-board-label">${_esc(label)} <span>${list.length}</span></div>
      <div class="cmd-board-list">${shown.length
        ? shown.map(_renderProdTaskCard).join('')
        : `<div class="cmd-empty">${_esc(empty)}</div>`}</div>
    </div>`;
  };
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="task_board">
    ${_panelHeader('Tasks', 'task_board')}
    <div class="cmd-panel-b" id="cmd-task-board">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <span style="font-size:9px;color:#5a6470;">${total} total</span>
        <button type="button" class="cmd-board-open-tasks" data-action="tasks">All Tasks →</button>
      </div>
      <input type="text" id="cmd-prod-add" class="cmd-prod-add" placeholder="+ new task (enter to add)" autocomplete="off" />
      <div class="cmd-board-counts">
        <span class="cmd-board-count open">${open.length} OPEN</span>
        <span class="cmd-board-count blocked">${blocked.length} BLOCKED</span>
        <span class="cmd-board-count done">${done.length} DONE</span>
      </div>
      ${section('OPEN', open, 'No open tasks.')}
      ${section('BLOCKED', blocked, 'Nothing blocked.')}
      ${section('DONE', done, 'No completions yet.', 4)}
    </div>
  </section>`;
}

function _renderMemFocus(data) {
  const notes = data.notes_preview || [];
  const pinned = notes.filter((n) => n.pinned).length;
  const brief = data.ceo_brief || {};
  const status = brief.status || 'missing';
  const content = brief.content || '';
  let bodyHtml = '';
  if (content) {
    try {
      bodyHtml = mdToHtml(content);
    } catch (_) {
      bodyHtml = `<pre>${_esc(content)}</pre>`;
    }
  }
  const kicker = brief.title
    ? `${brief.title}${status === 'stale' ? ' · stale' : ''}`
    : 'CEO Brief';
  const showCompile = status !== 'ready';
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="mem_focus">
    ${_panelHeader('Selected', 'mem_focus')}
    <div class="cmd-panel-b" id="cmd-mem-focus">
      ${content ? `
        <div class="cmd-mem-brief-kicker">${_esc(kicker)}</div>
        <div class="cmd-mem-brief-md">${bodyHtml}</div>
      ` : `
        <div class="cmd-mem-focus-copy">
          No CEO brief for today yet. Compile gathers chron outputs into one rundown.
          Pin from Notes · ${pinned} pinned · ${notes.length} recent in rail.
        </div>
      `}
      ${showCompile ? '<button type="button" class="cmd-mem-brief" data-action="ceo_brief">COMPILE BRIEF</button>' : ''}
      <div class="cmd-mem-focus-actions">
        <button type="button" class="cmd-cmd-btn" data-action="notes">Notes</button>
        <button type="button" class="cmd-cmd-btn" data-action="library">Library</button>
        <button type="button" class="cmd-cmd-btn" data-action="research">Research</button>
      </div>
    </div>
  </section>`;
}

function _renderDirectivePanel(data) {
  const hero = data.hero || DATA.hero;
  const { open, blocked, done, total } = _bucketProdQueue(data);
  const tp = data.today_plan || {};
  const sum = tp.summary || {};
  const blurb = (hero.branch === 'prod' && hero.explain)
    ? hero.explain
    : 'Application materials, directives, and scheduled prod work. Act from the board on the left.';
  const triageBits = [];
  if (sum.stale) triageBits.push(`${sum.stale} stale`);
  if (sum.overdue) triageBits.push(`${sum.overdue} overdue`);
  if (sum.fat) triageBits.push(`${sum.fat} fat`);
  const meta = triageBits.length
    ? `${triageBits.join(' · ')} · ${sum.open_items || 0} open items`
    : `${open.length} open · ${blocked.length} blocked · ${done.length} done · ${total} live`;
  const planLabel = sum.total
    ? `Plan Today (${sum.total}) →`
    : 'Plan Today →';
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="directive">
    ${_panelHeader('Directive', 'directive')}
    <div class="cmd-panel-b" id="cmd-directive">
      <div class="cmd-directive-mark">PROD</div>
      <div class="cmd-directive-blurb">${_esc(blurb)}</div>
      <div class="cmd-directive-meta">${_esc(meta)}</div>
      ${hero.cta_label && hero.branch === 'prod' ? `
        <button type="button" class="cmd-mem-brief" data-action="${_esc(hero.action || '')}" data-id="${_esc(hero.target_id || '')}">
          ${_esc(hero.cta_label)} →
        </button>` : ''}
      <button type="button" class="cmd-mem-brief" data-action="plan_today">${_esc(planLabel)}</button>
    </div>
  </section>`;
}

function _branchHealth(data, branchId) {
  return (data?.branch_health || []).find((b) => b.id === branchId) || null;
}

function _domainTabAttention(data, tab) {
  const ids = DOMAIN_TAB_BRANCH_IDS[tab] || [];
  let count = 0;
  let hot = false;
  for (const id of ids) {
    const bh = _branchHealth(data, id);
    if (!bh) continue;
    count += Number(bh.count) || 0;
    const st = String(bh.state || '').toLowerCase();
    if (st === 'busy' || st === 'attention' || st === 'armed') hot = true;
  }
  return { count, hot, show: hot || count > 0 };
}

function _globeGraphStats(data) {
  const graph = data?.globe_graph || {};
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const meta = graph.meta || {};
  const byKind = {};
  for (const n of nodes) {
    const k = String(n.kind || 'other');
    byKind[k] = (byKind[k] || 0) + 1;
  }
  return {
    nodeCount: meta.node_count ?? nodes.length,
    edgeCount: meta.edge_count ?? edges.length,
    mempalace: meta.mempalace || '',
    byKind,
  };
}

function _renderJobCard(job, tier) {
  const company = job.company || 'Company';
  const role = job.role || 'Role';
  const status = job.status || '';
  return `
    <div class="cmd-job-card" data-tier="${_esc(tier)}" data-action="jobs" data-id="${_esc(job.id || '')}">
      <div class="cmd-job-card-h">
        <span class="cmd-job-title" title="${_esc(`${company} — ${role}`)}">${_esc(company)} — ${_esc(role)}</span>
      </div>
      ${status ? `<div class="cmd-job-meta">${_esc(status)}</div>` : ''}
    </div>`;
}

function _renderAgencyBoard(data) {
  const detail = data.jobs_detail || {};
  const ready = detail.ready_to_apply || [];
  const review = detail.needs_review || [];
  const agents = (data.agent_activity || []).filter((a) => !a.swarm);
  const section = (label, list, empty, tier) => `
    <div class="cmd-board-section">
      <div class="cmd-board-label">${_esc(label)} <span>${list.length}</span></div>
      <div class="cmd-board-list">${list.length
    ? list.map((j) => _renderJobCard(j, tier)).join('')
    : `<div class="cmd-empty">${_esc(empty)}</div>`}</div>
    </div>`;
  const agentBlock = agents.length
    ? `<div class="cmd-board-section">
        <div class="cmd-board-label">Agent runs <span>${agents.length}</span></div>
        <div class="cmd-board-list">${_renderAgentActivity(agents)}</div>
      </div>`
    : '';
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="agency_board">
    ${_panelHeader('Jobs & Agents', 'agency_board')}
    <div class="cmd-panel-b" id="cmd-agency-board">
      <div class="cmd-board-counts">
        <span class="cmd-board-count due">${review.length} REVIEW</span>
        <span class="cmd-board-count open">${ready.length} READY</span>
        <button type="button" class="cmd-board-open-tasks" data-action="jobs">Open Jobs →</button>
      </div>
      ${section('NEEDS REVIEW', review, 'Nothing waiting for review.', 'review')}
      ${section('READY TO APPLY', ready, 'Pipeline clear — no ready jobs.', 'ready')}
      ${agentBlock}
      ${detail.headline ? `<div class="cmd-board-foot">${_esc(detail.headline)}</div>` : ''}
    </div>
  </section>`;
}

function _renderAgencyFocus(data) {
  const detail = data.jobs_detail || {};
  const ready = (detail.ready_to_apply || []).length;
  const review = (detail.needs_review || []).length;
  const bh = _branchHealth(data, 'agency');
  const blurb = detail.headline || bh?.summary || 'Review applications and dispatch agency work.';
  const commands = _filterCommandsForTab(data.commands, 'AGENCY');
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="agency_focus">
    ${_panelHeader('AM Report', 'agency_focus')}
    <div class="cmd-panel-b" id="cmd-agency-focus">
      <div class="cmd-directive-mark">AGENCY</div>
      <div class="cmd-directive-blurb">${_esc(blurb)}</div>
      <div class="cmd-directive-meta">${ready} ready · ${review} review · ${(bh?.state || 'idle').toUpperCase()}</div>
      <button type="button" class="cmd-mem-brief" data-action="jobs">Review Jobs →</button>
      <div class="cmd-mem-focus-actions" style="margin-top:8px;">
        ${_renderCommands(commands)}
      </div>
    </div>
  </section>`;
}

function _renderRelayBoard(data) {
  const focus = _renderBranchFocus(data, 'RELAY');
  const board = data.relay_board;
  let body;
  if (board && (board.needs_attention || board.claimed_stuck || board.in_progress)) {
    const sections = [];
    const stuck = board.claimed_stuck || [];
    const needs = board.needs_attention || [];
    const flight = board.in_progress || [];
    if (stuck.length) {
      sections.push(`<div class="cmd-relay-bucket-label">Stuck</div>${_renderDirectives(stuck)}`);
    }
    if (needs.length) {
      sections.push(`<div class="cmd-relay-bucket-label">Needs pickup</div>${_renderDirectives(needs)}`);
    }
    if (flight.length) {
      sections.push(`<div class="cmd-relay-bucket-label">In flight</div>${_renderDirectives(flight)}`);
    }
    body = sections.length
      ? sections.join('<div style="margin-top:10px;"></div>')
      : '<div class="cmd-empty">Clear deck — nothing queued</div>';
  } else {
    const queue = _filterByBranch(data.directives || data.priority_queue, 'RELAY');
    body = _renderDirectives(queue);
  }
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="relay_board">
    ${_panelHeader('Handoff Queue', 'relay_board')}
    <div class="cmd-panel-b" id="cmd-relay-board">
      ${focus}
      <div style="margin-top:8px;">${body}</div>
      <button type="button" class="cmd-notes-open" data-action="agent_bin" style="margin-top:8px;">Open Agent Bin →</button>
    </div>
  </section>`;
}

function _renderRelayStats(data) {
  const bh = _branchHealth(data, 'relay') || {};
  const stats = data.relay_stats || {};
  const attention = Number((data.counts || {}).handoffs_attention ?? bh.count ?? 0);
  const inFlight = Number((data.counts || {}).handoffs_in_progress ?? 0);
  const stuck = Number((data.counts || {}).handoffs_claimed_stuck ?? (data.relay_board?.counts?.claimed_stuck) ?? 0);
  const commands = _filterCommandsForTab(data.commands, 'RELAY')
    .filter((c) => c.action === 'agent_bin' || c.action === 'relay_watcher');
  const closeRate = stats.close_rate == null
    ? '—'
    : `${Math.round(Number(stats.close_rate) * 100)}%`;
  const rows = [
    ['Waiting', attention],
    ['Stuck', stuck],
    ['In flight', inFlight],
    ['Issued (7d)', stats.issued ?? '—'],
    ['Completed', stats.completed ?? '—'],
    ['Failed', stats.failed ?? '—'],
    ['Open', stats.open ?? '—'],
    ['Close rate', closeRate],
    ['State', String(bh.state || 'idle').toUpperCase()],
  ].map(([label, val]) => `
    <div class="cmd-relay-stat-row"><span>${_esc(label)}</span><span>${_esc(String(val))}</span></div>`).join('');
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="relay_stats">
    ${_panelHeader('Relay Stats', 'relay_stats')}
    <div class="cmd-panel-b" id="cmd-relay-stats">
      <div class="cmd-directive-blurb">${_esc(bh.summary || 'Handoff relay health')}</div>
      ${rows}
      <div class="cmd-mem-focus-actions" style="margin-top:10px;">
        ${_renderCommands(commands)}
      </div>
    </div>
  </section>`;
}

function _filterCommsPreview(preview, filter = _commsInboxFilter) {
  const rows = preview || [];
  if (filter === 'all') return rows;
  if (filter === 'triage') return rows.filter((m) => m.urgent || (m.score || 0) >= 2);
  return rows.filter((m) => !m.is_read);
}

function _commsInboxMeta(preview, filtered) {
  const all = preview || [];
  const shown = filtered || [];
  if (!all.length) return 'No recent mail';
  const unread = all.filter((m) => !m.is_read).length;
  const triage = all.filter((m) => m.urgent || (m.score || 0) >= 2).length;
  if (_commsInboxFilter === 'triage') return `${shown.length} need triage`;
  if (_commsInboxFilter === 'all') return `${shown.length} recent · ${unread} unread`;
  return `${shown.length} unread${triage ? ` · ${triage} need triage` : ''}`;
}

function _renderCommsInboxFilters() {
  return `<div class="cmd-comms-filters">${COMMS_INBOX_FILTERS.map(([id, label]) =>
    `<button type="button" class="cmd-comms-filter${id === _commsInboxFilter ? ' is-active' : ''}" data-comms-filter="${id}">${label}</button>`
  ).join('')}</div>`;
}

function _renderCommsInboxBody(data) {
  const preview = data.comms_preview || [];
  const bh = _branchHealth(data, 'comms');
  const filtered = _filterCommsPreview(preview);
  const cards = filtered.length
    ? filtered.map((m) => `
      <div class="cmd-comms-card" data-urgent="${m.urgent ? '1' : '0'}" data-unread="${m.is_read ? '0' : '1'}" data-action="${_esc(m.action || 'email')}" data-id="${_esc(m.id || m.uid || '')}">
        <div class="cmd-comms-card-h">
          <span class="cmd-comms-subject" title="${_esc(m.subject)}">${_esc(m.subject)}</span>
        </div>
        ${m.from ? `<div class="cmd-comms-from">${_esc(m.from)}</div>` : ''}
        ${m.reason ? `<div class="cmd-comms-from">${_esc(m.reason)}</div>` : ''}
      </div>`).join('')
    : `<div class="cmd-empty">${_esc(
      preview.length
        ? 'No messages match this filter'
        : (bh?.summary || 'Inbox ready — open email to sync.')
    )}</div>`;
  return `
    ${_renderCommsInboxFilters()}
    <div class="cmd-notes-meta">${_esc(_commsInboxMeta(preview, filtered))}</div>
    <div class="cmd-notes-list">${cards}</div>`;
}

function _renderCommsInbox(data) {
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="comms_inbox">
    ${_panelHeader('Inbox', 'comms_inbox')}
    <div class="cmd-panel-b" id="cmd-comms-inbox">
      ${_renderCommsInboxBody(data)}
    </div>
  </section>`;
}

function _renderCommsFocus(data) {
  const bh = _branchHealth(data, 'comms') || {};
  const preview = data.comms_preview || [];
  const focus = data.comms_focus || {};
  const urgent = preview.filter((m) => m.urgent).length;
  const converted = Number(focus.conversion_count);
  const windowDays = Number(focus.conversion_window_days) || 7;
  const commands = _filterCommandsForTab(data.commands, 'COMMS')
    .filter((c) => c.action === 'email');
  const top = preview[0];
  const conversionLine = Number.isFinite(converted)
    ? `${converted} converted to reminders · last ${windowDays}d`
    : '';
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="comms_focus">
    ${_panelHeader('Message Focus', 'comms_focus')}
    <div class="cmd-panel-b" id="cmd-comms-focus">
      <div class="cmd-directive-mark">COMMS</div>
      <div class="cmd-directive-blurb">${_esc(bh.summary || 'Email and inbox briefs')}</div>
      <div class="cmd-directive-meta">${bh.count || preview.length || 0} unread · ${urgent} need triage</div>
      ${conversionLine ? `<div class="cmd-directive-meta">${_esc(conversionLine)}</div>` : ''}
      ${top ? `
        <div class="cmd-mem-focus-copy">
          Top: <strong>${_esc(top.subject)}</strong>${top.from ? ` — ${_esc(top.from)}` : ''}
        </div>` : `
        <div class="cmd-mem-focus-copy">Open Inbox to read mail or run Inbox Brief for a voice rundown.</div>`}
      <button type="button" class="cmd-mem-brief" data-action="email">Open Inbox →</button>
      <div class="cmd-mem-focus-actions" style="margin-top:8px;">
        ${_renderCommands(commands)}
      </div>
    </div>
  </section>`;
}

function _renderMyceliaPulse(feed) {
  const pulse = feed?.pulse || [];
  if (!pulse.length) return '';
  return `<div class="cmd-board-section" style="margin-top:10px;">
    <div class="cmd-board-label">Pulse</div>
    ${pulse.slice(0, 6).map((p) => `
      <div class="cmd-myc-pulse-row" data-action="${p.source_kind === 'note' ? 'open_note' : 'open_doc'}" data-id="${_esc(p.source_id || '')}">
        <span class="cmd-myc-pulse-agent">${_esc(p.agent || 'Agent')}</span>
        <span class="cmd-myc-pulse-text">${_esc(p.excerpt || p.did || p.sensed || '—')}</span>
      </div>`).join('')}
  </div>`;
}

function _renderMyceliaHealth(feed) {
  const health = feed?.health || {};
  if (!health.summary) return '';
  const warn = health.fragmented ? ' data-attn="true"' : '';
  return `<div class="cmd-myc-health"${warn} title="Blackboard substrate health">
    <span class="cmd-myc-health-label">Substrate</span>
    <span class="cmd-myc-health-text">${_esc(health.summary || 'healthy')}</span>
  </div>`;
}

function _renderMyceliaSignals(data) {
  const feed = data.mycelia_feed || {};
  const signals = feed.signals || [];
  const body = signals.length
    ? signals.map((s) => `
      <div class="cmd-myc-signal-row${s.for_human ? ' cmd-myc-signal-human' : ''}"
        data-action="${_esc(s.action || 'open_doc')}" data-id="${_esc(s.source_id || '')}">
        <div class="cmd-myc-signal-meta">${_esc(s.date || '')} · ${_esc(s.agent || 'agent')} → ${_esc(s.target || 'guild')}</div>
        <div class="cmd-myc-signal-text">${_esc(s.text || '')}</div>
      </div>`).join('')
    : '<div class="cmd-empty">No recent SIGNAL lines — swarm is quiet</div>';
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="mycelia_signals">
    ${_panelHeader('Swarm Signals', 'mycelia_signals')}
    <div class="cmd-panel-b" id="cmd-mycelia-signals">
      ${_renderMyceliaHealth(feed)}
      ${body}
    </div>
  </section>`;
}

function _renderMyceliaFruit(data) {
  const feed = data.mycelia_feed || {};
  const fruit = feed.fruit || {};
  const pending = fruit.pending || [];
  const fruits = fruit.fruits || [];
  let body = '';
  if (pending.length) {
    body += `<div class="cmd-board-section"><div class="cmd-board-label">Pending at gate</div>
      ${pending.map((p) => `<div class="cmd-myc-fruit-row"><span>${_esc(p.item || '?')}</span><span>${_esc(p.status || '')}</span></div>`).join('')}
    </div>`;
  }
  if (fruits.length) {
    body += `<div class="cmd-board-section"><div class="cmd-board-label">Recent fruit</div>
      ${fruits.map((f) => `<div class="cmd-myc-fruit-row"><span>${_esc(f.fruit || '')}</span></div>`).join('')}
    </div>`;
  }
  if (!body) {
    body = '<div class="cmd-empty">No fruit logged yet — Herald runs at 21:00 ET</div>';
  }
  const ledgerId = fruit.ledger_id || '';
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="mycelia_fruit">
    ${_panelHeader('Fruit Ledger', 'mycelia_fruit')}
    <div class="cmd-panel-b" id="cmd-mycelia-fruit">
      ${body}
      ${ledgerId ? `<button type="button" class="cmd-mem-brief" data-action="open_doc" data-id="${_esc(ledgerId)}">Open ledger →</button>` : ''}
    </div>
  </section>`;
}

function _renderCeoQuickRead(data) {
  const lines = data.mycelia_feed?.quick_read || [];
  if (!lines.length) return '';
  return `<div class="cmd-quick-read" id="cmd-quick-read" data-cmd-vis="hero">
    <div class="cmd-quick-read-label">Quick read</div>
    <ul class="cmd-quick-read-list">
      ${lines.map((l) => `<li class="cmd-quick-read-item" data-kind="${_esc(l.kind || '')}">${_esc(l.text || '')}</li>`).join('')}
    </ul>
  </div>`;
}

function _renderMyceliaActivity(data) {
  const feed = data.mycelia_feed || {};
  const swarm = (data.agent_activity || []).filter((a) => a.swarm);
  const stats = _globeGraphStats(data);
  const kinds = Object.entries(stats.byKind)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([k, n]) => `<div class="cmd-graph-kind"><span>${_esc(k)}</span><span>${n}</span></div>`)
    .join('');
  const activity = swarm.length
    ? _renderAgentActivity(swarm)
    : '<div class="cmd-empty">No swarm runs yet — dispatch from the Mycelia deck</div>';
  return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="mycelia_activity">
    ${_panelHeader('Swarm Activity', 'mycelia_activity')}
    <div class="cmd-panel-b" id="cmd-mycelia-activity">
      ${activity}
      ${_renderMyceliaPulse(feed)}
      ${kinds ? `<div class="cmd-board-section" style="margin-top:10px;">
        <div class="cmd-board-label">Graph nodes</div>
        ${kinds}
      </div>` : ''}
    </div>
  </section>`;
}

function _renderMyceliaStats(data) {
  const stats = _globeGraphStats(data);
  const kinds = Object.entries(stats.byKind)
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `<div class="cmd-graph-kind"><span>${_esc(k)}</span><span>${n}</span></div>`)
    .join('');
  return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="mycelia_stats">
    ${_panelHeader('Graph Stats', 'mycelia_stats')}
    <div class="cmd-panel-b" id="cmd-mycelia-stats">
      <div class="cmd-graph-stat-grid">
        <div class="cmd-graph-stat">${stats.nodeCount}<span>NODES</span></div>
        <div class="cmd-graph-stat">${stats.edgeCount}<span>EDGES</span></div>
      </div>
      ${stats.mempalace ? `<div class="cmd-notes-meta">MemPalace · ${_esc(stats.mempalace)}</div>` : ''}
      ${kinds || '<div class="cmd-empty">Graph empty</div>'}
    </div>
  </section>`;
}

function _renderPanelById(id, data, tab) {
  switch (id) {
    case 'branch_focus':
      return _renderBranchFocus(data, tab);
    case 'vitals':
      return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="vitals">
        ${_panelHeader('System Vitals', 'vitals')}
        <div class="cmd-panel-b" id="cmd-vitals">${_renderVitals(data.vitals)}</div>
      </section>`;
    case 'priority_queue': {
      const queue = tab === 'CORE'
        ? (data.directives || data.priority_queue)
        : _filterByBranch(data.directives || data.priority_queue, tab);
      return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="priority_queue">
        ${_panelHeader(tab === 'CORE' ? 'Priority Queue' : `${tab} Queue`, 'priority_queue')}
        <div class="cmd-panel-b" id="cmd-directives">${_renderDirectives(queue)}</div>
      </section>`;
    }
    case 'swarm_activity':
      if (!(data.agent_activity && data.agent_activity.length)) return '';
      return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="swarm_activity">
        ${_panelHeader('Swarm Activity', 'swarm_activity')}
        <div class="cmd-panel-b" id="cmd-agent-activity">${_renderAgentActivity(data.agent_activity)}</div>
      </section>`;
    case 'documents':
      return `<section class="cmd-panel" data-tab="queue" data-cmd-vis="documents">
        ${_panelHeader('Documents', 'documents')}
        <div class="cmd-panel-b" id="cmd-documents">${_renderDocs(data.documents)}</div>
      </section>`;
    case 'notes_rail':
      return _renderNotesRail(data);
    case 'task_board':
      return _renderTaskBoard(data);
    case 'command_deck': {
      const commands = _filterCommandsForTab(data.commands, tab);
      const suggested = tab === 'CORE' ? data.suggested_commands : [];
      return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="command_deck">
        ${_panelHeader(tab === 'CORE' ? 'Command Deck' : `${tab} Deck`, 'command_deck')}
        <div class="cmd-panel-b">
          ${_renderSuggested(suggested)}
          <div class="cmd-cmds" id="cmd-commands">${_renderCommands(commands)}</div>
        </div>
      </section>`;
    }
    case 'audio_io': {
      const audio = data.audio || DATA.audio;
      return `<section class="cmd-panel" data-tab="commands" data-cmd-vis="audio_io" style="flex:0 0 auto;">
        ${_panelHeader('Audio I/O', 'audio_io')}
        <div class="cmd-panel-b">
          <div class="cmd-audio" id="cmd-audio" data-state="standby" role="button" tabindex="0" aria-label="Activate Jarvis voice">
            <span class="cmd-audio-dot"></span>
            <span id="cmd-audio-label">${_esc(audio.label || 'TTS Standby')}</span>
            <button type="button" class="cmd-audio-lock" id="cmd-audio-lock" title="Toggle voice lock (hold the floor)" aria-label="Toggle voice lock">Lock</button>
          </div>
          <div class="cmd-audio-hint">${_esc(audio.hint || 'Tap to arm Jarvis · Lock holds the floor · Alt+Shift+V')}</div>
        </div>
      </section>`;
    }
    case 'ai_wire': {
      const wire = tab === 'CORE' ? data.wire : _filterByBranch(data.wire, tab);
      return `<section class="cmd-panel" data-tab="wire" data-cmd-vis="ai_wire">
        ${_panelHeader(tab === 'CORE' ? 'AI Wire' : `${tab} Wire`, 'ai_wire')}
        <div class="cmd-panel-b" id="cmd-wire">${_renderWire(wire)}</div>
      </section>`;
    }
    case 'mem_focus':
      return _renderMemFocus(data);
    case 'directive':
      return _renderDirectivePanel(data);
    case 'agency_board':
      return _renderAgencyBoard(data);
    case 'agency_focus':
      return _renderAgencyFocus(data);
    case 'relay_board':
      return _renderRelayBoard(data);
    case 'relay_stats':
      return _renderRelayStats(data);
    case 'comms_inbox':
      return _renderCommsInbox(data);
    case 'comms_focus':
      return _renderCommsFocus(data);
    case 'mycelia_activity':
      return _renderMyceliaActivity(data);
    case 'mycelia_signals':
      return _renderMyceliaSignals(data);
    case 'mycelia_fruit':
      return _renderMyceliaFruit(data);
    case 'mycelia_stats':
      return _renderMyceliaStats(data);
    default:
      return '';
  }
}

function _renderLeftRailPanels(data, tab = _domainTab) {
  const layout = TAB_LAYOUT[tab] || TAB_LAYOUT.CORE;
  return (layout.left || []).map((id) => _renderPanelById(id, data, tab)).join('');
}

function _renderRightRailPanels(data, tab = _domainTab) {
  const layout = TAB_LAYOUT[tab] || TAB_LAYOUT.CORE;
  return (layout.right || []).map((id) => _renderPanelById(id, data, tab)).join('');
}

function _paintDomainRails(root, data = _data) {
  if (!root) return;
  root.dataset.domainTab = _domainTab;
  root.querySelectorAll('#cmd-domain-tabs .cmd-domain-tab').forEach((b) => {
    b.setAttribute('aria-pressed', b.dataset.domainTab === _domainTab ? 'true' : 'false');
  });
  const select = root.querySelector('#cmd-domain-select');
  if (select && select.value !== _domainTab) select.value = _domainTab;

  // Live sync must not destroy notes search / prod-add while the operator types.
  if (cmdEditableOwnsFocus()) {
    _applyVisibilityPrefs(root);
    _updateMobileEmptyHints(root);
    _updateDomainTabDots(root, data);
    return;
  }

  const focusSnap = captureCmdEditableFocus();
  const left = root.querySelector('.cmd-rail[data-cmd-rail="left"]');
  const right = root.querySelector('.cmd-rail[data-cmd-rail="right"]');
  if (left) {
    const toggle = left.querySelector('.cmd-rail-toggle');
    const toggleHtml = toggle ? toggle.outerHTML : '';
    left.innerHTML = `${toggleHtml}<div id="cmd-left-panels">${_renderLeftRailPanels(data, _domainTab)}</div>`;
  }
  if (right) {
    const toggle = right.querySelector('.cmd-rail-toggle');
    const toggleHtml = toggle ? toggle.outerHTML : '';
    right.innerHTML = `${toggleHtml}<div id="cmd-right-panels">${_renderRightRailPanels(data, _domainTab)}</div>`;
  }
  _applyVisibilityPrefs(root);
  _updateMobileEmptyHints(root);
  _updateDomainTabDots(root, data);
  _wireNotesSearch(root);
  _wireProdTaskBoard(root);
  restoreCmdEditableFocus(focusSnap);
}

function _wireNotesSearch(root) {
  const input = root.querySelector('#cmd-notes-search');
  if (!input || input.dataset.wired === '1') return;
  input.dataset.wired = '1';
  input.addEventListener('input', () => {
    const q = String(input.value || '').trim().toLowerCase();
    root.querySelectorAll('#cmd-notes-list .cmd-note-card').forEach((card) => {
      const hay = card.dataset.search || '';
      card.hidden = !!(q && !hay.includes(q));
    });
  });
}

function _wireProdTaskBoard(root) {
  const input = root.querySelector('#cmd-prod-add');
  if (input && input.dataset.wired !== '1') {
    input.dataset.wired = '1';
    input.addEventListener('keydown', async (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const title = String(input.value || '').trim();
      if (!title) return;
      input.disabled = true;
      try {
        await _addProdOrbitalTask(title);
        input.value = '';
      } finally {
        input.disabled = false;
        input.focus();
      }
    });
  }
}

async function _addProdOrbitalTask(title, sourceNoteId = null) {
  const due = new Date(Date.now() + 7 * 86400_000).toISOString();
  try {
    const payload = {
      title,
      content: '',
      note_type: 'todo',
      label: 'directive queued',
      due_date: due,
      pinned: false,
      source: 'cmd_center',
      task_status: 'queued',
    };
    const from = sourceNoteId != null ? String(sourceNoteId).trim() : '';
    if (from) payload.promoted_from = from;
    const res = await fetch(`${API_BASE}/api/notes`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    window.uiModule?.showToast?.('Task added');
    await _fetchData();
    _paint();
  } catch (err) {
    console.warn('add prod task failed', err);
    window.uiModule?.showToast?.('Could not add task');
  }
}

async function _moveProdOrbitalTask(id, nextStatus, kind = '') {
  if (!id || !nextStatus || !PROD_TASK_STATUSES.has(nextStatus)) return;

  let snaps = _loadProdOrbitalDoneSnap();
  const { all } = _bucketProdQueue(_data);
  const live = all.find((t) => t.id === String(id));
  const snapSrc = live || snaps.find((s) => String(s.id) === String(id));

  if (nextStatus === 'done' && snapSrc) {
    snaps = [{ ...snapSrc, status: 'done' }, ...snaps.filter((s) => String(s.id) !== String(id))];
    _saveProdOrbitalDoneSnap(snaps);
  } else if (nextStatus !== 'done') {
    snaps = snaps.filter((s) => String(s.id) !== String(id));
    _saveProdOrbitalDoneSnap(snaps);
  }

  // Optimistic local hint (no longer source of truth — cleared after server write).
  const map = _loadProdOrbitalStatusMap();
  map[String(id)] = nextStatus;
  _saveProdOrbitalStatusMap(map);

  const itemKind = kind || snapSrc?.kind || 'note';
  if (itemKind === 'note' || itemKind === '') {
    try {
      const res = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}`, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_status: nextStatus }),
      });
      if (res.ok) {
        delete map[String(id)];
        _saveProdOrbitalStatusMap(map);
        _prodStatusBackfilled.add(String(id));
      }
    } catch (err) {
      console.warn('prod task_status PUT failed', err);
    }
  }

  await _fetchData();
  _paint();
}

function _setDomainTab(tab) {
  if (!DOMAIN_TABS.includes(tab)) return;
  _domainTab = tab;
  _persistDomainTab(tab);
  const root = document.getElementById('cmd-center-root');
  if (!root) return;
  _paintDomainRails(root, _data);
}

function _wireDomainTabs(root) {
  const select = root.querySelector('#cmd-domain-select');
  if (select && select.dataset.wired !== '1') {
    select.dataset.wired = '1';
    select.addEventListener('change', () => { _setDomainTab(select.value); });
  }
  const nav = root.querySelector('#cmd-domain-tabs');
  if (!nav || nav.dataset.wired === '1') return;
  nav.dataset.wired = '1';
  nav.addEventListener('click', (e) => {
    const btn = e.target.closest('.cmd-domain-tab');
    if (!btn) return;
    e.preventDefault();
    _setDomainTab(btn.dataset.domainTab);
  });
  _wireNotesSearch(root);
}

function _isWireExpanded() {
  try { return sessionStorage.getItem(WIRE_EXPANDED_KEY) === '1'; } catch { return false; }
}

function _setWireExpanded(expanded) {
  try { sessionStorage.setItem(WIRE_EXPANDED_KEY, expanded ? '1' : '0'); } catch { /* ignore */ }
}

function _readRailsCollapsed() {
  try {
    const raw = localStorage.getItem(RAILS_COLLAPSED_KEY);
    if (!raw) return { left: false, right: false };
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      return { left: !!parsed.left, right: !!parsed.right };
    }
  } catch { /* ignore */ }
  return { left: false, right: false };
}

function _writeRailsCollapsed(state) {
  try { localStorage.setItem(RAILS_COLLAPSED_KEY, JSON.stringify(state)); } catch { /* ignore */ }
}

function _isVoiceMuted() {
  try { return localStorage.getItem(VOICE_MUTE_KEY) === '1'; } catch { return false; }
}

function _setVoiceMuted(muted) {
  try { localStorage.setItem(VOICE_MUTE_KEY, muted ? '1' : '0'); } catch { /* ignore */ }
  setVoiceEnabled(!muted);
}

function _mapBriefHighlight(hl) {
  // HQ_HOOK_HIGHLIGHT — call highlightNodes from scene when brief fires
  if (!hl || !hl.type) return;
  if (hl.type === 'overdue') {
    highlightNodes({ status: 'overdue' }, 3500);
  } else if (hl.type === 'domain') {
    highlightNodes({ branch: String(hl.domain || '').toLowerCase() }, 3500);
  } else if (hl.type === 'all') {
    highlightNodes({ branch: 'prod' }, 2000);
    setTimeout(() => highlightNodes({ branch: 'agency' }, 2000), 120);
  }
}

function _ensureAudio() {
  initCmdCenterAudio({
    onHighlight: _mapBriefHighlight,
    onClearHighlight: () => clearHighlights(),
    onNowText: (t) => {
      const el = document.getElementById('cmd-now-text');
      if (el) el.textContent = t || '';
    },
    onState: (s) => {
      const audio = document.getElementById('cmd-audio');
      if (audio) audio.dataset.state = s;
      const btn = document.getElementById('cmd-brief-btn');
      if (btn) {
        btn.classList.toggle('playing', s === 'speaking');
        btn.textContent = s === 'speaking' ? 'STOP' : 'BRIEF ME';
      }
    },
  });
  setVoiceEnabled(!_isVoiceMuted());
  window.__cmdBrief = () => runBrief({ script: (_data && _data.brief_script) || [] });
}

function _applyLiveConnectionUi(state) {
  const root = document.getElementById('cmd-center-root');
  if (!root) return;

  let host = document.getElementById('cmd-live-banner-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'cmd-live-banner-host';
    const header = root.querySelector('.cmd-topbar');
    header?.insertAdjacentElement('afterend', host);
  }
  host.innerHTML = renderLiveBanner(state, { lastSyncedAt: _syncedAt });

  if (state === 'offline') _paintSyncChrome({ text: 'offline', stale: true });
  else if (state === 'stale') _paintSyncChrome({ stale: true });
  else _paintSyncChrome({ stale: false });
}

function _applyLiveUpdate(payload) {
  if (!_open) return;
  const data = payload || _data;
  try {
    const voiceRealtime = window.voiceRealtimeModule;
    if (voiceRealtime?.isConnected?.() && voiceRealtime?.isJarvisMode?.()) {
      voiceRealtime.reapplyVaultBrief?.({ force: true });
    }
  } catch (_) { /* ignore */ }

  const cardsUpdated = _updateStageCardsInPlace(data.stage_cards);
  if (!cardsUpdated) {
    // Full remount would steal caret from notes search / prod-add — defer.
    if (cmdEditableOwnsFocus()) return;
    _paint();
    return;
  }
  _paintSyncChrome();
  _refreshHandoffPanelsInPlace(data);
  updateCmdCenterScene(
    data.branch_health || [],
    data.counts?.handoffs_in_progress || 0,
    data.globe_graph,
  );
  _updateCardAnchors();
}

function _startLiveUpdates() {
  stopCmdCenterLive();
  // HQ_HOOK_LIVE_START
  startCmdCenterLive({
    intervalMs: 30000,
    fetchData: async () => {
      const unchanged = await _fetchData({ live: true });
      if (_fetchError) throw new Error(_fetchError);
      return unchanged ? { unchanged: true } : _data;
    },
    applyUpdate: (data) => {
      if (data && data.unchanged) {
        // Nothing changed server-side — refresh only the sync label, skip
        // the full stage/rail re-render (see vault-live-sync-efficiency).
        _paintSyncChrome();
        return;
      }
      _applyLiveUpdate(data || _data);
    },
    onConnectionChange: (state) => {
      _applyLiveConnectionUi(state);
      if (state === 'offline') {
        try { earconError(); } catch (_) { /* ignore */ }
      } else if (state === 'live') {
        try { earconMsg(); } catch (_) { /* ignore */ }
      }
    },
  });
}

function _glanceStats(data) {
  const hero = data?.hero || DATA.hero;
  const counts = data?.counts || {};
  const unit = String(hero.unit || '').toUpperCase();
  const attention = unit === 'OVERDUE' || unit === 'HANDOFFS'
    ? (Number(hero.value) || 0)
    : (Number(counts.handoffs_attention) || Number(hero.value) || 0);
  const inFlight = Number(counts.handoffs_in_progress) || 0;
  const upNext = (data?.stage_cards || []).find((c) => c.id === 'up_next');
  const agenda = data?.agenda || {};
  let today = (upNext?.subtitle || '').trim();
  if (!today && agenda.today_events != null) {
    today = `${agenda.today_events} event${agenda.today_events === 1 ? '' : 's'}`;
  }
  if (!today) today = '—';
  return { attention, inFlight, today };
}

function _renderGlance(data) {
  const g = _glanceStats(data);
  return `
    <div class="cmd-glance" id="cmd-glance" data-cmd-vis="hero">
      <span class="cmd-glance-chip" data-attn="${g.attention > 0 ? 'true' : 'false'}">Attention<strong>${_esc(String(g.attention))}</strong></span>
      <span class="cmd-glance-chip">In flight<strong>${_esc(String(g.inFlight))}</strong></span>
      <span class="cmd-glance-chip" title="${_esc(g.today)}">Today<strong>${_esc(g.today)}</strong></span>
    </div>`;
}

function _renderNowBar(data) {
  const muted = _isVoiceMuted();
  const audio = data?.audio || DATA.audio;
  const statusLine = audio.label || 'Standby · orb + glance · BRIEF ME when ready';
  return `
    <footer class="cmd-now-bar" id="cmd-now-bar">
      <button type="button" class="cmd-brief-btn" id="cmd-brief-btn" title="Start briefing">BRIEF ME</button>
      <div class="cmd-now-text" id="cmd-now-text">${_esc(statusLine)}</div>
      <div class="cmd-now-actions">
        <button type="button" class="cmd-voice-mute" id="cmd-voice-mute" aria-pressed="${muted ? 'true' : 'false'}" title="Mute voice">${muted ? 'UNMUTE' : 'MUTE'}</button>
        <button type="button" class="cmd-earcon-demo" id="cmd-earcon-demo" title="Demo earcon">EARCON</button>
      </div>
    </footer>`;
}

function _railToggleLabel(side, collapsed) {
  if (side === 'left') return collapsed ? '›' : '‹';
  return collapsed ? '‹' : '›';
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
      const dedupAttr = c.dedup_key ? ` data-dedup-key="${_esc(c.dedup_key)}"` : '';
      return `<button type="button" class="cmd-cmd-btn" data-action="${_esc(c.action)}"${idAttr}${dedupAttr}>${_esc(c.label)}</button>`;
    }).join('')}
  `).join('');
}

function _renderAgentActivity(list) {
  if (!list?.length) return '<div class="cmd-empty">No agent runs yet — dispatch one from the Mycelia deck</div>';
  const rawParts = list
    .map((a) => (a.raw || '').trim())
    .filter(Boolean);
  const lines = list.map((a) => {
    const st = (a.status || '').toLowerCase();
    const icon = a.icon || (st === 'error' ? '!' : (st === 'success' || st === 'completed' || st === 'ok' ? '✓' : '·'));
    const idle = !(st === 'success' || st === 'completed' || st === 'ok' || st === 'error' || st === 'running');
    const stClass = st === 'error' ? 'err' : (idle || st === 'running' ? 'idle' : '');
    const label = a.label || a.agent || (a.text || '').replace(/^[✓!·⋯✗]\s*/, '') || 'Agent';
    const ago = _formatRelative(a.ts);
    return `
    <div class="cmd-swarm-line" data-action="${_esc(a.action || 'open_task')}" data-id="${_esc(a.target_id || '')}" data-state="${_esc(a.status || '')}">
      <span class="cmd-swarm-st ${stClass}">${_esc(icon)}</span>
      <span class="cmd-swarm-w" title="${_esc(label)}">${_esc(label)}</span>
      <span class="cmd-swarm-ago">${_esc(ago ? (ago === 'just now' ? 'just now' : `${ago} ago`) : '—')}</span>
    </div>`;
  }).join('');
  const rawBlock = rawParts.length
    ? `<button type="button" class="cmd-raw-toggle" id="cmd-swarm-raw-btn" aria-expanded="false">View raw log →</button>
       <div class="cmd-raw-log" id="cmd-swarm-raw-log">${_esc(rawParts.join('\n---\n'))}</div>`
    : '';
  return `<div class="cmd-swarm">${lines}${rawBlock}</div>`;
}

function _renderWire(list) {
  if (!list?.length) return '<div class="cmd-empty">Wire quiet</div>';
  const expanded = _isWireExpanded();
  const visible = expanded ? list : list.slice(0, 3);
  const rows = visible.map((w) => {
    const rel = _formatRelative(w.ts);
    const ago = !rel ? '—' : (rel === 'just now' ? 'just now' : `${rel} ago`);
    return `
    <div class="cmd-wire-item" data-action="${_esc(w.action || '')}" data-id="${_esc(w.target_id || '')}">
      <span class="cmd-wire-ts">${_esc(ago)}</span>
      <span class="cmd-wire-tag">${_esc((w.branch || '').toUpperCase())}</span>
      <span title="${_esc(w.text)}">${_esc(w.text)}</span>
    </div>`;
  }).join('');
  let toggle = '';
  if (list.length > 3) {
    toggle = expanded
      ? `<button type="button" class="cmd-wire-toggle" id="cmd-wire-toggle" aria-expanded="true">Collapse wire</button>`
      : `<button type="button" class="cmd-wire-toggle" id="cmd-wire-toggle" aria-expanded="false">Show wire (${list.length})</button>`;
  }
  return `<div class="cmd-wire">${rows}${toggle}</div>`;
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

/** A card duplicates another surface's primary CTA when it has a dedup_key
 * (a priority_queue item claims it) but isn't the one flagged primary —
 * i.e. the hero (or another slot) already owns that item's "next action". */
function _isPassiveCard(c) {
  return !!c.dedup_key && !c.primary;
}

function _renderStageCards(cards) {
  const positions = ['tl', 'tr', 'bl', 'br', 'ml'];
  return (cards || []).slice(0, 5).map((c, i) => `
    <div class="cmd-float-card${_isPassiveCard(c) ? ' cmd-float-card--passive' : ''}" data-pos="${positions[i] || 'tl'}" data-action="${_esc(c.action || '')}" data-id="${_esc(c.target_id || '')}" data-branch="${_esc(_cardBranch(c))}" data-dedup-key="${_esc(c.dedup_key || '')}" data-primary="${c.primary ? 'true' : 'false'}">
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
    el.dataset.dedupKey = c.dedup_key || '';
    el.dataset.primary = c.primary ? 'true' : 'false';
    el.classList.toggle('cmd-float-card--passive', _isPassiveCard(c));
    const label = el.querySelector('.cmd-float-label');
    const sub = el.querySelector('.cmd-float-sub');
    if (label) label.textContent = c.label || '';
    if (sub) sub.textContent = c.subtitle || '';
  });
  return true;
}

function _refreshHandoffPanelsInPlace(data) {
  const root = document.getElementById('cmd-center-root');
  if (root) _paintDomainRails(root, data);

  const hero = data.hero || DATA.hero;
  const heroEl = document.getElementById('cmd-hero');
  if (heroEl) {
    heroEl.dataset.action = hero.action || '';
    heroEl.dataset.id = hero.target_id || '';
    heroEl.dataset.attn = (hero.unit || '').toUpperCase() === 'OVERDUE' ? 'overdue' : '';
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

  const statusList = _statusForRender(data);
  const statusStrip = document.getElementById('cmd-status-strip');
  if (statusStrip) statusStrip.innerHTML = _renderStatus(statusList);

  _updateDomainTabDots(document.getElementById('cmd-center-root'), data);

  const glanceEl = document.getElementById('cmd-glance');
  if (glanceEl) {
    const wrap = document.createElement('div');
    wrap.innerHTML = _renderGlance(data);
    const next = wrap.firstElementChild;
    if (next) glanceEl.replaceWith(next);
  }

  const nowText = document.getElementById('cmd-now-text');
  if (nowText && data.audio?.label) nowText.textContent = data.audio.label;
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
  const stale = _syncedAt && (Date.now() - new Date(_syncedAt).getTime() > 60000);
  const statusList = _statusForRender(data);
  const rails = _readRailsCollapsed();

  const errBanner = _fetchError
    ? `<div class="cmd-error-banner"><span>${_esc(_fetchError)}</span><button type="button" data-action="refresh">Vault Sync</button></div>`
    : '';

  return `
    <div class="cmd-center-root" id="cmd-center-root" data-mobile-tab="${_esc(_mobileTab)}" data-domain-tab="${_esc(_domainTab)}">
      <div class="cmd-mobile-grabber notes-mobile-grabber" aria-hidden="true"></div>
      <header class="cmd-topbar">
        <div class="cmd-brand">
          <div class="cmd-brand-title">${_esc(data.title || DATA.title)}</div>
          <div class="cmd-brand-sub">${_esc(data.subtitle || DATA.subtitle)}</div>
        </div>
        ${_renderDomainTabs(data)}
        <div class="cmd-topbar-spacer"></div>
        <div class="cmd-clock-wrap">
          <div class="cmd-clock" id="cmd-center-clock">00:00:00</div>
          <div class="cmd-date" id="cmd-center-date"></div>
          <div class="cmd-sync" id="cmd-sync-label" data-action="refresh" data-stale="${stale ? 'true' : 'false'}">${_esc(_syncLabel())}</div>
        </div>
        <button type="button" class="cmd-sync-btn" id="cmd-vault-sync" data-action="refresh" data-stale="${stale ? 'true' : 'false'}" title="Vault Sync" aria-label="Vault Sync">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        </button>
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
        <div class="cmd-status-strip" id="cmd-status-strip" data-tab="hud" data-cmd-vis="status_pills">${_renderStatus(statusList)}</div>
        <aside class="cmd-rail" data-cmd-rail="left" data-rail-collapsed="${rails.left ? 'true' : 'false'}">
          <button type="button" class="cmd-rail-toggle" data-rail-side="left" title="${rails.left ? 'Expand left rail' : 'Collapse left rail'}" aria-label="${rails.left ? 'Expand left rail' : 'Collapse left rail'}">${_railToggleLabel('left', rails.left)}</button>
          <div id="cmd-left-panels">${_renderLeftRailPanels(data, _domainTab)}</div>
        </aside>

        <section class="cmd-stage" id="cmd-stage" data-tab="hud">
          <div id="cmd-scene-mount" data-cmd-vis="globe_scene"></div>
          <div class="cmd-scene-auto" id="cmd-scene-auto" data-cmd-vis="globe_scene" data-on="true" role="button" tabindex="0" aria-label="Toggle globe auto-spin" title="Toggle auto-spin (double-click empty space to reset)">⟳ AUTO</div>
          <div class="cmd-stage-cards-wrap" id="cmd-stage-cards-wrap" data-cmd-vis="stage_cards" data-tab="hud">${_renderStageCards(data.stage_cards)}</div>
          ${_renderGlance(data)}
          ${_renderCeoQuickRead(data)}
          <div class="cmd-hero" id="cmd-hero" data-cmd-vis="hero" data-tab="hud" data-attn="${_esc((hero.unit || '').toUpperCase() === 'OVERDUE' ? 'overdue' : '')}" data-action="${_esc(hero.action || '')}" data-id="${_esc(hero.target_id || '')}">
            <div class="cmd-hero-label">${_esc(hero.label || '')}</div>
            <div class="cmd-hero-title">${_esc(hero.title || '')}</div>
            <div class="cmd-hero-value"><span id="cmd-hero-num">0</span><span class="cmd-hero-unit">${_esc(hero.unit || '')}</span></div>
            <div class="cmd-hero-explain">${_esc(hero.explain || '')}</div>
            <div class="cmd-hero-vel">${_esc(hero.velocity || '')}</div>
            ${hero.cta_label ? `<span class="cmd-hero-cta">${_esc(hero.cta_label)} →</span>` : ''}
          </div>
        </section>

        <aside class="cmd-rail" data-cmd-rail="right" data-rail-collapsed="${rails.right ? 'true' : 'false'}">
          <button type="button" class="cmd-rail-toggle" data-rail-side="right" title="${rails.right ? 'Expand right rail' : 'Collapse right rail'}" aria-label="${rails.right ? 'Expand right rail' : 'Collapse right rail'}">${_railToggleLabel('right', rails.right)}</button>
          <div id="cmd-right-panels">${_renderRightRailPanels(data, _domainTab)}</div>
        </aside>
      </div>
      ${_renderNowBar(data)}
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
  _paintSyncChrome();
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

function _pauseSceneAndClock() {
  pauseCmdCenterScene();
  stopCmdCenterLive();
  // HQ_HOOK_LIVE_STOP
  stopBrief();
  destroyCmdCenterAudio();
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
  _ensureAudio();
  _startLiveUpdates();
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

async function _refreshAfterTriage() {
  await _fetchData();
  if (!_open) return;
  const cardsUpdated = _updateStageCardsInPlace(_data.stage_cards);
  if (!cardsUpdated) {
    _paint();
    return;
  }
  _refreshHandoffPanelsInPlace(_data);
  updateCmdCenterScene(
    _data.branch_health || [],
    _data.counts?.handoffs_in_progress || 0,
    _data.globe_graph,
  );
  _updateCardAnchors();
  _paintSyncChrome();
}

function _triageStackFromPayload() {
  const stack = Array.isArray(_data.attention_stack) ? _data.attention_stack.filter(Boolean) : [];
  if (stack.length) return stack;
  // Fallback if Python payload is stale (pre-widen): mirror directive notes + handoffs/jobs.
  const queue = Array.isArray(_data.priority_queue) ? _data.priority_queue : [];
  const fromQueue = queue.filter((i) => i && ['note', 'handoff', 'job'].includes(i.kind));
  if (fromQueue.length) {
    return fromQueue.map((item) => ({
      id: item.id,
      kind: item.kind,
      title: item.title,
      subtitle: item.subtitle || '',
      preview: item.subtitle || '',
      branch: item.branch,
      status: item.status || 'calm',
      due_label: item.due_label || '',
      urgency: item.urgency,
      action: item.action,
      target_id: item.target_id || item.id,
      due_at: item.due_at,
    }));
  }
  const dirs = Array.isArray(_data.directives) ? _data.directives : [];
  return dirs.map((d) => ({
    id: d.id,
    kind: 'note',
    title: d.title,
    subtitle: d.subtitle || '',
    preview: d.subtitle || '',
    branch: d.branch || 'prod',
    status: d.status || 'calm',
    due_label: d.due_label || '',
    action: d.action || 'open_note',
    target_id: d.target_id || d.id,
  })).filter((d) => d.id);
}

function _openDirectiveTriageFromHero() {
  const stack = _triageStackFromPayload();
  if (!stack.length) {
    window.uiModule?.showToast?.('Nothing to triage', 2200);
    return false;
  }
  return openDirectiveTriage({
    stack,
    mount: document.getElementById('cmd-center-root') || document.getElementById(PANE_ID),
    onRefresh: _refreshAfterTriage,
    onOpenItem: (action, id) => _runAction(action, id),
  });
}

function _todayPlanSummaryLine(plan) {
  const sum = plan?.summary || {};
  const bits = [];
  if (sum.stale) bits.push(`${sum.stale} stale`);
  if (sum.overdue) bits.push(`${sum.overdue} overdue`);
  if (sum.due) bits.push(`${sum.due} due`);
  if (sum.fat) bits.push(`${sum.fat} fat checklists`);
  if (sum.open_items) bits.push(`${sum.open_items} open items`);
  if (!bits.length) return sum.total ? `${sum.total} items to triage` : 'Nothing queued — deck is clear';
  return bits.join(' · ');
}

function _renderTodayPlanRow(item) {
  const band = String(item.band || 'open');
  const openN = Number(item.open_items) || 0;
  const metaBits = [];
  if (item.stale && item.missed_days) metaBits.push(`missed ${item.missed_days}d`);
  if (openN) metaBits.push(`${openN} open item${openN === 1 ? '' : 's'}`);
  if (item.due_label) metaBits.push(item.due_label);
  if (item.pinned) metaBits.push('pinned');
  const id = item.target_id || item.id || '';
  return `
    <div class="cmd-today-row" data-band="${_esc(band)}" data-note-id="${_esc(id)}">
      <div class="cmd-today-row-h">
        <div class="cmd-today-row-title" data-plan-act="open" data-id="${_esc(id)}" title="Open note">${_esc(item.title || 'Untitled')}</div>
        <span class="cmd-today-band">${_esc(band)}</span>
      </div>
      ${metaBits.length ? `<div class="cmd-today-meta">${_esc(metaBits.join(' · '))}</div>` : ''}
      ${item.preview ? `<div class="cmd-today-preview">${_esc(item.preview)}</div>` : ''}
      <div class="cmd-today-actions">
        <button type="button" class="cmd-today-btn" data-plan-act="open" data-id="${_esc(id)}">Open</button>
        <button type="button" class="cmd-today-btn" data-plan-act="delegate" data-id="${_esc(id)}">Delegate</button>
        <button type="button" class="cmd-today-btn" data-plan-act="block" data-id="${_esc(id)}" data-title="${_esc(item.title || 'Focus')}">Block 50m</button>
        <button type="button" class="cmd-today-btn" data-plan-act="archive" data-id="${_esc(id)}">Archive</button>
        <div class="cmd-today-delegate" data-delegate-for="${_esc(id)}">
          <button type="button" class="cmd-today-btn" data-plan-act="handoff" data-id="${_esc(id)}" data-target="cursor">Cursor</button>
          <button type="button" class="cmd-today-btn" data-plan-act="handoff" data-id="${_esc(id)}" data-target="claude">Claude</button>
          <button type="button" class="cmd-today-btn" data-plan-act="handoff" data-id="${_esc(id)}" data-target="hermes">Hermes</button>
          <button type="button" class="cmd-today-btn" data-plan-act="handoff" data-id="${_esc(id)}" data-target="odysseus">Odysseus</button>
        </div>
      </div>
    </div>`;
}

function _closeTodayPlanSheet() {
  document.getElementById('cmd-today-backdrop')?.remove();
}

function _openTodayPlanSheet() {
  const host = document.getElementById('cmd-center-pane') || document.getElementById('cmd-center-root')?.parentElement;
  if (!host) {
    window.uiModule?.showToast?.('Command Center not ready');
    return;
  }
  _closeTodayPlanSheet();
  const plan = _data.today_plan || { summary: {}, items: [] };
  const items = Array.isArray(plan.items) ? plan.items : [];
  const backdrop = document.createElement('div');
  backdrop.id = 'cmd-today-backdrop';
  backdrop.className = 'cmd-today-backdrop';
  backdrop.innerHTML = `
    <div class="cmd-today-sheet" role="dialog" aria-modal="true" aria-labelledby="cmd-today-title">
      <div class="cmd-today-head">
        <div class="cmd-today-head-text">
          <div class="cmd-today-kicker">Prod · Triage</div>
          <div class="cmd-today-title" id="cmd-today-title">Plan Today</div>
          <div class="cmd-today-summary">${_esc(_todayPlanSummaryLine(plan))}</div>
        </div>
        <button type="button" class="cmd-today-close" data-plan-act="close" aria-label="Close">✕</button>
      </div>
      <div class="cmd-today-body">
        ${items.length
          ? items.map(_renderTodayPlanRow).join('')
          : '<div class="cmd-today-empty">No stale briefs, overdue notes, or fat checklists.<br/>Left-rail Tasks stay calm.</div>'}
      </div>
      <div class="cmd-today-foot">
        <button type="button" class="cmd-mem-brief" data-plan-act="notes">Open Notes</button>
        <button type="button" class="cmd-today-btn" data-plan-act="refresh" style="padding:8px 10px;">Refresh</button>
      </div>
    </div>`;
  host.style.position = host.style.position || 'relative';
  host.appendChild(backdrop);

  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) _closeTodayPlanSheet();
  });
  backdrop.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-plan-act]');
    if (!btn || !backdrop.contains(btn)) return;
    e.preventDefault();
    e.stopPropagation();
    const act = btn.dataset.planAct;
    const id = btn.dataset.id || '';
    if (act === 'close') {
      _closeTodayPlanSheet();
      return;
    }
    if (act === 'notes') {
      _closeTodayPlanSheet();
      notesModule?.openNotes?.();
      return;
    }
    if (act === 'refresh') {
      await _fetchData();
      _paint();
      _openTodayPlanSheet();
      return;
    }
    if (act === 'open' && id) {
      _closeTodayPlanSheet();
      if (notesModule?.openNote) await notesModule.openNote(id);
      else notesModule?.openNotes?.();
      return;
    }
    if (act === 'delegate' && id) {
                  const menu = backdrop.querySelector(`.cmd-today-delegate[data-delegate-for="${id.replace(/"/g, '')}"]`);
      backdrop.querySelectorAll('.cmd-today-delegate.is-open').forEach((el) => {
        if (el !== menu) el.classList.remove('is-open');
      });
      menu?.classList.toggle('is-open');
      return;
    }
    if (act === 'handoff' && id) {
      const target = btn.dataset.target || 'cursor';
      try {
        const res = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}/handoff`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        window.uiModule?.showToast?.(`Delegated → ${target}`, 3500);
        const row = btn.closest('.cmd-today-row');
        row?.remove();
        await _fetchData();
        _paint();
      } catch (err) {
        console.warn('today plan handoff failed', err);
        window.uiModule?.showToast?.('Handoff failed');
      }
      return;
    }
    if (act === 'archive' && id) {
      try {
        const res = await fetch(`${API_BASE}/api/notes/${encodeURIComponent(id)}`, {
          method: 'PUT',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ archived: true }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        window.uiModule?.showToast?.('Archived', 3000);
        btn.closest('.cmd-today-row')?.remove();
        await _fetchData();
        _paint();
      } catch (err) {
        console.warn('today plan archive failed', err);
        window.uiModule?.showToast?.('Archive failed');
      }
      return;
    }
    if (act === 'block' && id) {
      const title = btn.dataset.title || 'Focus block';
      const start = new Date();
      start.setMinutes(0, 0, 0);
      start.setHours(start.getHours() + 1);
      const end = new Date(start.getTime() + 50 * 60 * 1000);
      const pad = (n) => String(n).padStart(2, '0');
      const tzMin = -start.getTimezoneOffset();
      const sign = tzMin >= 0 ? '+' : '-';
      const tz = `${sign}${pad(Math.floor(Math.abs(tzMin) / 60))}:${pad(Math.abs(tzMin) % 60)}`;
      const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00${tz}`;
      try {
        const res = await fetch(`${API_BASE}/api/calendar/events`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            summary: `Focus · ${title}`.slice(0, 120),
            dtstart: iso(start),
            dtend: iso(end),
            all_day: false,
            description: `From Command Center PLAN TODAY · note ${id}`,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        window.uiModule?.showToast?.('50m focus block booked', 3500);
        window.dispatchEvent(new CustomEvent('calendar-refresh'));
      } catch (err) {
        console.warn('today plan block failed', err);
        window.uiModule?.showToast?.('Could not book focus block');
      }
    }
  });
}

async function _runAction(action, id) {
  if (!action) return;
  console.debug('[CMD Center]', action, id || '');

  if (action === 'refresh') {
    if (_syncInFlight) return;
    _syncInFlight = true;
    _setHeaderSyncBusy(true);
    try {
      await _fetchData({ syncCalendar: true });
      window.dispatchEvent(new CustomEvent('calendar-refresh'));
      _paint();
    } finally {
      _syncInFlight = false;
      _setHeaderSyncBusy(false);
    }
    return;
  }

  if (action === 'plan_today') {
    _openTodayPlanSheet();
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
  if (action === 'ceo_brief') {
    if (_domainTab !== 'MEM') _setDomainTab('MEM');
    const existing = _data.ceo_brief || {};
    if (existing.status === 'ready') {
      try {
        const res = await fetch(`${API_BASE}/api/home/ceo-brief/latest`, { credentials: 'same-origin' });
        const payload = await res.json().catch(() => ({}));
        if (res.ok && payload.content) {
          _data.ceo_brief = { ...existing, ...payload, status: payload.status || 'ready' };
        }
      } catch (_) { /* keep the cmd-center excerpt */ }
      window.uiModule?.showToast?.("Today's CEO brief is ready", 2500);
      _setDomainTab('MEM');
      return;
    }
    window.uiModule?.showToast?.(
      existing.status === 'stale' ? 'Recompiling stale CEO brief…' : 'Compiling CEO brief…',
      2500,
    );
    try {
      const res = await fetch(`${API_BASE}/api/home/ceo-brief`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok || payload.ok === false) {
        window.uiModule?.showToast?.(
          payload.result || `CEO brief failed (${res.status})`,
        );
        return;
      }
      _data.ceo_brief = {
        status: payload.status || (payload.content ? 'ready' : 'missing'),
        id: payload.doc_id || payload.id || '',
        doc_id: payload.doc_id || payload.id || '',
        title: payload.title || 'CEO Brief',
        content: payload.content || '',
        updated_at: payload.updated_at,
        is_today: payload.is_today,
        stale: payload.stale,
        compiled: payload.compiled,
      };
      window.uiModule?.showToast?.(
        payload.compiled === false ? "Today's CEO brief is ready" : 'CEO brief ready',
        3500,
      );
      _setDomainTab('MEM');
    } catch (err) {
      console.warn('ceo_brief failed', err);
      window.uiModule?.showToast?.('CEO brief failed');
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

function _fireBrief() {
  const briefBtn = document.getElementById('cmd-brief-btn');
  if (briefBtn?.classList.contains('playing')) {
    stopBrief();
    return;
  }
  // HQ_HOOK_BRIEF_WIRE
  const script = (_data && _data.brief_script) || [];
  runBrief({ script });
}

function _wireClicks(root) {
  // Pane element survives _paint()'s innerHTML swaps — guard so each refresh
  // does not stack another delegated click listener (N paints ⇒ N opens).
  if (!root || root.dataset.cmdClicksWired === '1') return;
  root.dataset.cmdClicksWired = '1';
  // HQ_HOOK_BRIEF_WIRE
  root.addEventListener('click', (e) => {
    const briefBtn = e.target.closest('#cmd-brief-btn');
    if (briefBtn && root.contains(briefBtn)) {
      e.preventDefault();
      e.stopPropagation();
      _fireBrief();
      return;
    }
    const muteBtn = e.target.closest('#cmd-voice-mute');
    if (muteBtn && root.contains(muteBtn)) {
      e.preventDefault();
      e.stopPropagation();
      const next = muteBtn.getAttribute('aria-pressed') !== 'true';
      _setVoiceMuted(next);
      muteBtn.setAttribute('aria-pressed', next ? 'true' : 'false');
      muteBtn.textContent = next ? 'UNMUTE' : 'MUTE';
      const nowText = document.getElementById('cmd-now-text');
      if (nowText) nowText.textContent = next ? 'Voice muted' : (_data.audio?.label || 'Standby');
      return;
    }
    const earconBtn = e.target.closest('#cmd-earcon-demo');
    if (earconBtn && root.contains(earconBtn)) {
      e.preventDefault();
      e.stopPropagation();
      const nowText = document.getElementById('cmd-now-text');
      if (nowText) nowText.textContent = 'Earcon demo';
      earconDone();
      setTimeout(earconMsg, 600);
      setTimeout(earconAttn, 1100);
      setTimeout(earconError, 1600);
      return;
    }
    const railBtn = e.target.closest('.cmd-rail-toggle');
    if (railBtn && root.contains(railBtn)) {
      e.preventDefault();
      e.stopPropagation();
      const side = railBtn.dataset.railSide === 'right' ? 'right' : 'left';
      const rail = root.querySelector(`.cmd-rail[data-cmd-rail="${side}"]`);
      if (!rail) return;
      const collapsed = rail.getAttribute('data-rail-collapsed') !== 'true';
      rail.setAttribute('data-rail-collapsed', collapsed ? 'true' : 'false');
      railBtn.textContent = _railToggleLabel(side, collapsed);
      railBtn.title = collapsed ? `Expand ${side} rail` : `Collapse ${side} rail`;
      railBtn.setAttribute('aria-label', railBtn.title);
      const state = _readRailsCollapsed();
      state[side] = collapsed;
      _writeRailsCollapsed(state);
      requestAnimationFrame(_updateCardAnchors);
      return;
    }
    const wireToggle = e.target.closest('#cmd-wire-toggle');
    if (wireToggle && root.contains(wireToggle)) {
      e.preventDefault();
      e.stopPropagation();
      _setWireExpanded(!_isWireExpanded());
      const wireEl = document.getElementById('cmd-wire');
      if (wireEl) wireEl.innerHTML = _renderWire(_filterByBranch(_data.wire, _domainTab));
      return;
    }
    const rawBtn = e.target.closest('#cmd-swarm-raw-btn');
    if (rawBtn && root.contains(rawBtn)) {
      e.preventDefault();
      e.stopPropagation();
      const log = document.getElementById('cmd-swarm-raw-log');
      if (!log) return;
      const open = log.classList.toggle('show');
      rawBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      rawBtn.textContent = open ? 'Hide raw log ←' : 'View raw log →';
      return;
    }
    const statusPill = e.target.closest('.cmd-status-strip .cmd-pill');
    if (statusPill && root.contains(statusPill) && _isMobileViewport()) {
      const domain = PILL_BRANCH_TO_TAB[String(statusPill.dataset.branchId || '').toLowerCase()];
      if (domain) {
        e.preventDefault();
        e.stopPropagation();
        _setDomainTab(domain);
        return;
      }
    }
    const filterBtn = e.target.closest('[data-comms-filter]');
    if (filterBtn) {
      e.preventDefault();
      e.stopPropagation();
      _commsInboxFilter = filterBtn.dataset.commsFilter || 'unread';
      const panel = root.querySelector('#cmd-comms-inbox');
      if (panel) panel.innerHTML = _renderCommsInboxBody(_data);
      return;
    }
    const moveBtn = e.target.closest('[data-prod-move]');
    if (moveBtn && root.contains(moveBtn)) {
      e.preventDefault();
      e.stopPropagation();
      const next = moveBtn.dataset.prodMove || '';
      const id = moveBtn.dataset.id || '';
      const kind = moveBtn.dataset.kind || '';
      _moveProdOrbitalTask(id, next, kind);
      return;
    }
    const target = e.target.closest('[data-action]');
    if (!target || !root.contains(target)) return;
    // OPEN DIRECTIVE / hero CTA → always triage modal (never dump into Notes).
    const heroHit = target.id === 'cmd-hero' || target.closest('#cmd-hero');
    if (heroHit) {
      e.preventDefault();
      e.stopPropagation();
      _openDirectiveTriageFromHero();
      return;
    }
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

/**
 * True when some other surface already owns keyboard input — a text field,
 * the Directive Triage modal, or any modal that claims `data-cmd-modal-open`
 * on <body>. Global Space-hold / Esc stay silent in all three cases.
 */
function _inputOwnsFocus() {
  const active = document.activeElement;
  if (active) {
    const tag = active.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || active.isContentEditable) return true;
  }
  if (isDirectiveTriageOpen()) return true;
  if (document.body?.dataset.cmdModalOpen === 'true') return true;
  return false;
}

/**
 * Global Space-hold (arm voice) / Esc (dismiss vault) — bound once on
 * <document>, guarded by `_open` so they're inert while the vault is closed.
 * Matches the audio-panel hint copy ("Tap Audio or hold Space 3s ... Esc
 * dismisses vault") with real behavior instead of dead affordances.
 */
function _wireGlobalHotkeys() {
  if (_globalHotkeysWired) return;
  _globalHotkeysWired = true;

  _spaceHold = createSpaceHoldTracker({
    onArm: () => {
      if (!_open || _inputOwnsFocus()) return;
      _activateVoiceDelegate();
    },
  });

  document.addEventListener('keydown', (e) => {
    if (!_open) return;
    if (e.key === ' ' || e.code === 'Space') {
      if (_inputOwnsFocus()) return;
      // Only hijack default (page scroll) once the OS starts key-repeating —
      // a quick tap (no repeat events) never has its default prevented.
      if (e.repeat) e.preventDefault();
      _spaceHold.keydown();
      return;
    }
    if (e.key === 'Escape') {
      if (_inputOwnsFocus()) return;
      e.preventDefault();
      _closePanel('down');
    }
  });
  document.addEventListener('keyup', (e) => {
    if (e.key === ' ' || e.code === 'Space') _spaceHold?.release();
  });
  window.addEventListener('blur', () => _spaceHold?.release());
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
  _persistViewState(_mobileTab, _domainTab);
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
  const focusSnap = captureCmdEditableFocus();
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
  if (root) _wireDomainTabs(root);
  _tickClock();
  _animateHero(_data.hero?.value || 0);
  _mountScene();
  _ensureAudio();
  _setMobileTab(_mobileTab);
  // Error toasts / status labels must never steal focus — restore caret here.
  restoreCmdEditableFocus(focusSnap);
}

function _forceCloseCmdCenter() {
  _open = false;
  closeDirectiveTriage();
  _pauseSceneAndClock();
  disposeCmdCenterScene();
  clearHighlights();
  // HQ_HOOK_LIVE_STOP
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
  closeDirectiveTriage();
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
  clearHighlights();
  // HQ_HOOK_LIVE_STOP
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
  // View/domain preference persists across opens & reloads — don't reset to
  // 'hud' here (see vault-nav-model spec: preference survives reload).

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
  const root = document.getElementById('cmd-center-root');
  if (root) _wireDomainTabs(root);
  _setMobileTab(_mobileTab);

  _tickClock();
  _clockTimer = setInterval(_tickClock, 1000);
  _bindVoiceUi();
  _bindCmdActionFromVoice();
  _wireResizeReconcile();
  _wireGlobalHotkeys();

  Modals.register(PANEL_ID, {
    railBtnId: 'rail-cmd-center',
    sidebarBtnId: 'tool-cmd-center-btn',
    restoreFn: () => { openCmdCenter(); },
    closeFn: () => { _forceCloseCmdCenter(); },
  });

  await _fetchData({ syncCalendar: true });
  if (_open) {
    _paint();
    _startLiveUpdates();
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

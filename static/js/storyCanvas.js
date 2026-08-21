/**
 * Story Canvas — Odysseus shell panel (FormFlow / Notes pattern).
 * Embeds the React app at /static/story-canvas/ in a same-origin iframe so
 * session cookies and credentials: "same-origin" API calls work like Notes/Docs.
 */
import * as Modals from './modalManager.js';
import { collapseSidebarForMobileSheet, wireSwipeDismiss } from './panelSheet.js';
import { makeWindowDraggable } from './windowDrag.js';
import { applyEdgeDock } from './modalSnap.js';

const PANEL_ID = 'story-canvas-panel';

let _open = false;
let _pane = null;
let _backdrop = null;
let _keydownHandler = null;

const isMobileSheet = () => window.innerWidth <= 768;

function buildStoryCanvasUrl() {
  const lastId = localStorage.getItem('story-canvas:lastProjectId');
  const base = '/static/story-canvas/index.html';
  return lastId ? `${base}?project=${encodeURIComponent(lastId)}` : base;
}

function _ensureChipRegistered() {
  if (Modals.isRegistered(PANEL_ID)) return;
  Modals.register(PANEL_ID, {
    railBtnId: 'rail-story-canvas',
    sidebarBtnId: 'tool-story-canvas-btn',
    restoreFn: () => { openStoryCanvas(); },
    closeFn: () => { _forceClose(); },
  });
}

function _forceClose() {
  _open = false;
  document.body.classList.remove('story-canvas-view');
  try { window._restoreSidebarIfRouteCollapsed?.(); } catch (_) {}
  try { Modals.unregister(PANEL_ID); } catch (_) {}
  if (_keydownHandler) {
    document.removeEventListener('keydown', _keydownHandler);
    _keydownHandler = null;
  }
  try { _pane?.remove(); } catch (_) {}
  try { _backdrop?.remove(); } catch (_) {}
  _pane = null;
  _backdrop = null;
  const btn = document.getElementById('tool-story-canvas-btn');
  if (btn) btn.classList.remove('active');
}

export function isStoryCanvasOpen() {
  return _open;
}

export function openStoryCanvas({ newTab = false } = {}) {
  if (newTab) {
    window.open(buildStoryCanvasUrl(), '_blank', 'noopener');
    return;
  }

  if (_open) {
    const existing = document.getElementById('story-canvas-pane');
    if (existing) {
      try { existing.style.zIndex = String((Date.now() % 100000) + 200); } catch (_) {}
      return;
    }
    _open = false;
  }

  if (!document.getElementById('chat-container')) return;

  _open = true;
  document.body.classList.add('story-canvas-view');
  collapseSidebarForMobileSheet();

  const btn = document.getElementById('tool-story-canvas-btn');
  if (btn) btn.classList.add('active');

  document.querySelectorAll('#story-canvas-backdrop, #story-canvas-pane').forEach((el) => {
    try { el.remove(); } catch (_) {}
  });

  _backdrop = document.createElement('div');
  _backdrop.className = 'notes-pane-backdrop';
  _backdrop.id = 'story-canvas-backdrop';

  _pane = document.createElement('div');
  _pane.className = 'notes-pane story-canvas-pane';
  _pane.id = 'story-canvas-pane';
  _pane.setAttribute('role', 'dialog');
  _pane.setAttribute('aria-label', 'Story Canvas');

  _pane.innerHTML = `
    <div class="notes-mobile-grabber" aria-hidden="true"></div>
    <div class="notes-pane-header">
      <h4 class="notes-pane-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2.5px;margin-right:6px">
          <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 17.5h7M17.5 14v7"/>
        </svg>
        Story Canvas
      </h4>
      <span style="flex:1"></span>
      <button type="button" id="sc-open-tab" class="doc-action-icon-btn notes-header-text-btn" title="Open in new tab" style="opacity:0.8;gap:5px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        <span class="notes-header-btn-label">Tab</span>
      </button>
      <button id="sc-minimize-btn" class="modal-minimize-btn" title="Minimize" aria-label="Minimize Story Canvas" style="position:relative;left:2px;">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" aria-hidden="true"><line x1="6" y1="18" x2="18" y2="18"/></svg>
      </button>
      <button class="close-btn" id="sc-close" title="Close" aria-label="Close Story Canvas">\u2716</button>
    </div>
    <div class="sc-pane-body">
      <iframe class="sc-iframe" title="Story Canvas" src="${buildStoryCanvasUrl()}"></iframe>
    </div>
  `;

  if (isMobileSheet()) {
    _pane.style.position = 'fixed';
    _pane.style.inset = '0';
    _pane.style.width = '100%';
    _pane.style.maxWidth = '100%';
    _pane.style.zIndex = '170';
    _pane.style.borderRadius = '14px 14px 0 0';
    _pane.style.animation = 'sheet-enter 0.25s cubic-bezier(0.2, 0.8, 0.2, 1) both';
    _pane.style.transformOrigin = 'bottom center';
  }

  _backdrop.addEventListener('click', (ev) => {
    if (ev.target === _backdrop) closeStoryCanvas('down');
  });
  _backdrop.appendChild(_pane);
  document.body.appendChild(_backdrop);

  wireSwipeDismiss(_pane.querySelector('.notes-mobile-grabber'), _pane, () => closeStoryCanvas('down'));
  wireSwipeDismiss(_pane.querySelector('.notes-pane-header'), _pane, () => closeStoryCanvas('down'));

  _pane.querySelector('#sc-minimize-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeStoryCanvas('down');
  });
  _pane.querySelector('#sc-close')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeStoryCanvas();
  });
  _pane.querySelector('#sc-open-tab')?.addEventListener('click', () => {
    window.open(buildStoryCanvasUrl(), '_blank', 'noopener');
  });

  if (!isMobileSheet()) {
    makeWindowDraggable(_pane, {
      content: _pane,
      header: _pane.querySelector('.notes-pane-header'),
      skipSelector: 'button, input, select, textarea, label, .notes-mobile-grabber',
      enableDock: true,
      enableLeftDock: true,
    });
    applyEdgeDock(_pane, 'right');
  }

  if (_keydownHandler) {
    document.removeEventListener('keydown', _keydownHandler);
  }
  _keydownHandler = (e) => {
    if (!_open || e.key !== 'Escape') return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    e.preventDefault();
    closeStoryCanvas();
  };
  document.addEventListener('keydown', _keydownHandler);

  Modals.register(PANEL_ID, {
    railBtnId: 'rail-story-canvas',
    sidebarBtnId: 'tool-story-canvas-btn',
    restoreFn: () => { openStoryCanvas(); },
    closeFn: () => { _forceClose(); },
  });
}

export function closeStoryCanvas(direction) {
  if (!_open) return;
  _open = false;

  const minimize = direction === 'down';
  if (minimize) {
    _ensureChipRegistered();
  } else if (Modals.isRegistered(PANEL_ID)) {
    try { Modals.unregister(PANEL_ID); } catch (_) {}
  }

  if (_keydownHandler) {
    document.removeEventListener('keydown', _keydownHandler);
    _keydownHandler = null;
  }

  document.body.classList.remove('story-canvas-view');
  try { window._restoreSidebarIfRouteCollapsed?.(); } catch (_) {}

  const btn = document.getElementById('tool-story-canvas-btn');
  if (btn) btn.classList.remove('active');

  const pane = _pane || document.getElementById('story-canvas-pane');
  const backdrop = _backdrop || document.getElementById('story-canvas-backdrop');

  if (pane) {
    pane.classList.add('notes-pane-leaving');
    const cleanup = () => {
      try { pane.remove(); } catch (_) {}
      try { backdrop?.remove(); } catch (_) {}
      _pane = null;
      _backdrop = null;
    };
    pane.addEventListener('animationend', cleanup, { once: true });
    setTimeout(cleanup, 220);
  } else if (backdrop) {
    backdrop.remove();
    _backdrop = null;
  }

  if (minimize) {
    try { Modals.minimize(PANEL_ID); } catch (_) {}
  }
}

export function toggleStoryCanvas() {
  if (Modals.isMinimized(PANEL_ID)) {
    Modals.restore(PANEL_ID);
    return;
  }
  if (_open) closeStoryCanvas();
  else openStoryCanvas();
}

export function initStoryCanvas() {
  const tool = document.getElementById('tool-story-canvas-btn');
  if (tool && !tool.dataset.bound) {
    tool.dataset.bound = '1';
    tool.addEventListener('click', () => toggleStoryCanvas());
  }
  window.openStoryCanvas = openStoryCanvas;
  window.storyCanvasModule = {
    openStoryCanvas,
    closeStoryCanvas,
    toggleStoryCanvas,
    isStoryCanvasOpen: isStoryCanvasOpen,
  };
}

export default {
  openStoryCanvas,
  closeStoryCanvas,
  toggleStoryCanvas,
  isStoryCanvasOpen,
  initStoryCanvas,
};

/**
 * Selection → web search agents (provider picker + run).
 */

import uiModule from './ui.js';
import { bindMenuDismiss } from './escMenuStack.js';
import { openPanel as openResearchPanel } from './research/panel.js';
import * as researchJobs from './research/jobs.js';

const API_BASE = typeof window !== 'undefined' ? window.location.origin : '';

/** Preferred order; tinyfish first among paid/keyed for latency ROI. */
const SEARCH_AGENT_ORDER = [
  'tinyfish',
  'searxng',
  'duckduckgo',
  'brave',
  'tavily',
  'google_pse',
  'serper',
  'firecrawl',
  'perplexity',
];

const SEARCH_AGENT_LABELS = {
  tinyfish: 'TinyFish',
  searxng: 'SearXNG',
  duckduckgo: 'DuckDuckGo',
  brave: 'Brave Search',
  tavily: 'Tavily',
  google_pse: 'Google PSE',
  serper: 'Serper',
  firecrawl: 'Firecrawl',
  perplexity: 'Perplexity',
};

const _searchIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`;

let _providersCache = null;
let _providersFetchedAt = 0;
const PROVIDERS_TTL_MS = 60_000;

function _esc(text) {
  return uiModule?.esc?.(text) ?? String(text || '');
}

function _queryFromSelection(text, source) {
  const trimmed = String(text || '').trim();
  const firstLine = trimmed.split('\n').find((l) => l.trim()) || trimmed;
  return firstLine.trim().slice(0, 500) || trimmed.slice(0, 500);
}

function _contextNote(source, fullText) {
  const label = source?.label || 'Selection';
  const clipped = String(fullText || '').trim().slice(0, 1200);
  return clipped ? `${label}\n\n${clipped}` : label;
}

async function _fetchProviders() {
  const now = Date.now();
  if (_providersCache && now - _providersFetchedAt < PROVIDERS_TTL_MS) {
    return _providersCache;
  }
  try {
    const res = await fetch(`${API_BASE}/api/search/providers`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _providersCache = await res.json();
    _providersFetchedAt = now;
    return _providersCache;
  } catch {
    return _providersCache || [];
  }
}

function _mergeAgents(apiProviders) {
  const byId = new Map();
  for (const p of apiProviders || []) {
    if (!p?.id || p.id === 'disabled') continue;
    byId.set(p.id, {
      id: p.id,
      label: p.label || SEARCH_AGENT_LABELS[p.id] || p.id,
      available: !!p.available,
      kind: 'search',
    });
  }
  for (const id of SEARCH_AGENT_ORDER) {
    if (id === 'perplexity') {
      if (!byId.has(id)) {
        byId.set(id, {
          id,
          label: SEARCH_AGENT_LABELS.perplexity,
          available: true,
          kind: 'research',
        });
      } else {
        byId.get(id).kind = 'research';
      }
      continue;
    }
    if (!byId.has(id)) {
      byId.set(id, {
        id,
        label: SEARCH_AGENT_LABELS[id] || id,
        available: false,
        kind: 'search',
      });
    }
  }
  const ordered = [];
  for (const id of SEARCH_AGENT_ORDER) {
    const row = byId.get(id);
    if (row) ordered.push(row);
  }
  for (const [id, row] of byId) {
    if (!SEARCH_AGENT_ORDER.includes(id)) ordered.push(row);
  }
  return ordered;
}

function _positionMenu(menu, anchorRect, minWidth = 220) {
  const r = anchorRect || { left: 8, top: 8, bottom: 40, right: 40 };
  document.body.appendChild(menu);
  const mw = Math.max(minWidth, menu.offsetWidth || minWidth);
  let left = Math.min(r.left, window.innerWidth - mw - 8);
  left = Math.max(8, left);
  const mh = menu.offsetHeight || 200;
  const below = window.innerHeight - r.bottom;
  let top = (below < mh + 8 && r.top > mh + 8) ? (r.top - mh - 4) : (r.bottom + 4);
  top = Math.max(8, Math.min(top, window.innerHeight - mh - 8));
  menu.style.cssText += `position:fixed;z-index:11000;top:${Math.round(top)}px;left:${Math.round(left)}px;min-width:${mw}px;max-height:min(320px, calc(100vh - 16px));overflow-y:auto;`;
}

async function _runSearchProvider(provider, query, source, fullText) {
  uiModule?.showToast?.('Searching…', { duration: 12000, leadingIcon: 'spinner' });
  const fd = new FormData();
  fd.append('query', query);
  fd.append('provider', provider);
  fd.append('count', '8');
  const res = await fetch(`${API_BASE}/api/search/query`, {
    method: 'POST',
    body: fd,
    credentials: 'same-origin',
  });
  const data = await res.json().catch(() => ({}));
  if (data.error) throw new Error(data.error);
  const results = Array.isArray(data.results) ? data.results : [];
  const label = SEARCH_AGENT_LABELS[provider] || provider;
  if (!results.length) {
    uiModule?.showToast?.(`${label}: no results for “${query.slice(0, 60)}${query.length > 60 ? '…' : ''}”`);
    return;
  }
  const lines = results.slice(0, 4).map((r, i) => {
    const title = String(r.title || r.url || 'Result').slice(0, 72);
    return `${i + 1}. ${title}`;
  });
  const ctx = _contextNote(source, fullText);
  const body = [
    `${label} · ${results.length} result${results.length === 1 ? '' : 's'} · ${data.time ?? '?'}s`,
    '',
    `Query: ${query}`,
    '',
    lines.join('\n'),
    results.length > 4 ? `\n+${results.length - 4} more` : '',
    '',
    ctx ? `Context:\n${ctx}` : '',
  ].filter(Boolean).join('\n');
  try {
    await navigator.clipboard.writeText(body);
  } catch { /* optional */ }
  uiModule?.showToast?.(
    `${label}: ${results.length} result${results.length === 1 ? '' : 's'} (copied summary)`,
    { duration: 10000, leadingIcon: 'check' },
  );
}

async function _runPerplexity(query, source, fullText) {
  const prompt = [
    query,
    '',
    'Use this highlighted context from Odysseus when researching:',
    _contextNote(source, fullText),
  ].join('\n').trim();
  openResearchPanel();
  uiModule?.showToast?.('Starting Perplexity research…', { duration: 8000, leadingIcon: 'spinner' });
  await researchJobs.startJob(prompt, { research_engine: 'perplexity_agent' });
  uiModule?.showToast?.('Perplexity research running', {
    duration: 8000,
    action: 'Open research',
    onAction: () => openResearchPanel(),
  });
}

export async function runSelectionSearchAgent({ provider, text, source } = {}) {
  const query = _queryFromSelection(text, source);
  if (!query) throw new Error('Nothing to search');
  if (provider === 'perplexity') {
    await _runPerplexity(query, source, text);
    return;
  }
  await _runSearchProvider(provider, query, source, text);
}

export async function openSearchAgentMenu(anchorRect, { text, source } = {}) {
  document.querySelectorAll('.selection-search-menu-dropdown').forEach((d) => d.remove());
  const query = _queryFromSelection(text, source);
  if (!query) return;

  const menu = document.createElement('div');
  menu.className = 'note-corner-menu-dropdown note-handoff-menu-dropdown selection-search-menu-dropdown';
  menu.innerHTML = `
    <div class="note-handoff-menu-label">Web search agents</div>
    <div class="selection-search-query-preview">${_esc(query.length > 80 ? `${query.slice(0, 77)}…` : query)}</div>
    <div class="selection-search-agent-list"><div class="selection-search-loading">Loading providers…</div></div>`;

  _positionMenu(menu, anchorRect, 240);

  const close = bindMenuDismiss(menu, () => menu.remove(), (ev) => {
    const bar = document.querySelector('.selection-action-bar');
    return !menu.contains(ev.target) && !(bar && bar.contains(ev.target));
  });

  const listEl = menu.querySelector('.selection-search-agent-list');
  const agents = _mergeAgents(await _fetchProviders());
  listEl.innerHTML = '';

  for (const agent of agents) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ncm-item';
    btn.dataset.provider = agent.id;
    if (!agent.available && agent.kind === 'search') {
      btn.classList.add('selection-search-agent--unavailable');
      btn.disabled = true;
      btn.title = 'Configure API key or URL in Settings → Search';
    }
    btn.innerHTML = `${_searchIcon}<span>${_esc(agent.label)}</span>`;
    btn.addEventListener('click', async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      close();
      try {
        await runSelectionSearchAgent({ provider: agent.id, text, source });
      } catch (err) {
        console.error('Selection search failed', err);
        uiModule?.showError?.(err?.message || 'Search failed');
      }
    });
    listEl.appendChild(btn);
  }

  if (!listEl.children.length) {
    listEl.innerHTML = '<div class="selection-search-empty">No search agents configured</div>';
  }
}

export default {
  openSearchAgentMenu,
  runSelectionSearchAgent,
  SEARCH_AGENT_ORDER,
};

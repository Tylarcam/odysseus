/**
 * Cross-agent handoff packets — shared by slash commands and Notes UI.
 * Stored as Odysseus documents matching integrations handoff skill format.
 */

import uiModule from './ui.js';
import { bindMenuDismiss } from './escMenuStack.js';
import { openSearchAgentMenu, runSelectionSearchAgent } from './selectionSearch.js';

const HANDOFF_TITLE_PREFIX = 'handoff → ';
const _API_BASE = typeof window !== 'undefined' ? window.location.origin : '';
const HANDOFF_DOC_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const HANDOFF_VALID_TARGETS = new Set(['cursor', 'claude', 'odysseus', 'hermes']);
const HANDOFF_TARGET_ALIASES = {
  'claude-code': 'claude',
  claude_code: 'claude',
  cc: 'claude',
  'cursor-ide': 'cursor',
  cursor_ide: 'cursor',
  ody: 'odysseus',
  'odysseus-ui': 'odysseus',
  brudda: 'hermes',
};

export function normalizeHandoffTarget(name) {
  const key = String(name || '').trim().toLowerCase();
  return HANDOFF_TARGET_ALIASES[key] || key;
}

export function handoffDocTitle(target, title) {
  return `${HANDOFF_TITLE_PREFIX}${target}: ${String(title || '').trim()}`;
}

export function isHandoffDoc(doc) {
  const title = String(doc?.title || '').trim();
  return title.startsWith(HANDOFF_TITLE_PREFIX);
}

function handoffBootstrapBlock(target, project) {
  const lines = ['## Agent bootstrap', ''];
  const projectPath = String(project || '').trim();
  const isWindows = typeof navigator !== 'undefined' && /win/i.test(navigator.platform || navigator.userAgent || '');

  if (projectPath) {
    if (isWindows) {
      lines.push('```powershell', `cd "${projectPath}"`, '```', '');
    } else {
      lines.push('```bash', `cd ${JSON.stringify(projectPath)}`, '```', '');
    }
  }

  if (target === 'cursor') {
    lines.push('In Cursor, run the bootstrap block above, then execute **Next steps**.');
  } else if (target === 'claude') {
    lines.push('In Claude Code, run the bootstrap block above, then execute **Next steps**.');
  } else if (target === 'hermes') {
    lines.push(
      'In Hermes, run `handoff_api.py list --pending` or say **Pick up handoff**, then execute **Next steps**.',
    );
  } else {
    lines.push('In Odysseus, read **Goal** and **Next steps** — continue in chat or link the session.');
  }
  lines.push('');
  return lines.join('\n');
}

export function buildHandoffContent({
  source,
  target,
  project,
  goal,
  context,
  done,
  next,
  noteBody,
  sessionId,
}) {
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
  const frontmatter = [
    '---',
    'handoff_version: 1',
    `source: ${source}`,
    `target: ${target}`,
    'status: pending',
    `project: ${project || ''}`,
    `created_at: ${now}`,
  ];
  if (sessionId) frontmatter.push(`session_id: ${sessionId}`);
  frontmatter.push('---', '');

  const parts = [frontmatter.join('\n')];
  if (goal) parts.push(`## Goal\n\n${String(goal).trim()}\n`);
  if (context?.length) {
    parts.push('## Context', '');
    context.forEach(item => parts.push(`- ${item}`));
    parts.push('');
  }
  if (noteBody) parts.push(`## Notes\n\n${String(noteBody).trim()}\n`);
  if (done?.length) {
    parts.push('## Done so far', '');
    done.forEach(item => parts.push(`- ${item}`));
    parts.push('');
  }
  if (next?.length) {
    parts.push('## Next steps', '');
    next.forEach(item => parts.push(`- ${item}`));
    parts.push('');
  }
  parts.push(handoffBootstrapBlock(target, project));
  return parts.join('\n');
}

export async function createHandoffDocument({
  apiBase,
  target,
  title,
  goal,
  context = [],
  done = [],
  next = [],
  noteBody = '',
  project = '',
  source = 'odysseus',
  sessionId = '',
}) {
  const normalized = normalizeHandoffTarget(target);
  if (!HANDOFF_VALID_TARGETS.has(normalized)) {
    throw new Error(`Unknown handoff target "${target}"`);
  }

  const content = buildHandoffContent({
    source,
    target: normalized,
    project,
    goal,
    context,
    done,
    next,
    noteBody,
    sessionId,
  });

  const payload = {
    title: handoffDocTitle(normalized, title),
    content,
    language: 'markdown',
  };
  if (sessionId) payload.session_id = sessionId;

  const res = await fetch(`${apiBase}/api/document`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || 'Failed to create handoff');
  }

  const doc = await res.json();
  const docId = resolveHandoffDocId(doc);
  if (!docId) throw new Error('Handoff created but no valid document id returned');
  return {
    doc,
    docId,
    target: normalized,
    title: payload.title,
    relayStatus: doc?.handoff_relay?.status || null,
    noteId: doc?.handoff_relay?.note_id || null,
  };
}

/** Extract a canonical Odysseus handoff document UUID from an API payload. */
export function resolveHandoffDocId(doc) {
  const candidates = [
    doc?.id,
    doc?.document_id,
    doc?.doc_id,
    doc?.document?.id,
  ];
  for (const candidate of candidates) {
    const id = String(candidate || '').trim();
    if (HANDOFF_DOC_ID_RE.test(id)) return id;
  }
  return '';
}

export function handoffPickupHint(target, docId) {
  const id = resolveHandoffDocId({ id: docId }) || String(docId || '').trim();
  if (target === 'cursor') return `In Cursor, say: Pick up handoff ${id}`;
  if (target === 'claude') return `In Claude Code, say: Pick up handoff ${id}`;
  if (target === 'hermes') return `In Hermes, say: Pick up handoff ${id}`;
  return `Say: Pick up handoff ${id}`;
}

/** Paste-ready phrase for the receiving agent chat (Cursor skill trigger). */
export function handoffClipboardText(_target, docId) {
  const id = resolveHandoffDocId({ id: docId }) || String(docId || '').trim();
  return id ? `Pick up handoff ${id}` : '';
}

/**
 * Copy pickup phrase and show a long-lived toast after creating a handoff.
 * Keeps the pickup line visible and on the clipboard for paste into Cursor/Claude.
 */
export async function notifyHandoffPickup({ target, docId, noteId, relayStatus } = {}) {
  const normalized = normalizeHandoffTarget(target);
  const id = resolveHandoffDocId({ id: docId });
  if (!id) {
    uiModule?.showError?.('Handoff created but document id was missing or invalid');
    return;
  }

  const external = handoffTargetIsExternal(normalized);
  const clip = handoffClipboardText(normalized, id);
  let copied = false;
  if (clip) {
    try {
      await navigator.clipboard.writeText(clip);
      copied = true;
    } catch {
      copied = false;
    }
  }

  const agentLabel = {
    cursor: 'Cursor',
    claude: 'Claude Code',
    hermes: 'Hermes Agent : brudda',
    odysseus: 'Odysseus',
  }[normalized] || normalized;

  const headline = external
    ? (copied ? `Handoff → ${agentLabel} · copied to clipboard` : `Handoff → ${agentLabel}`)
    : (copied ? 'Odysseus relay started · copied to clipboard' : 'Odysseus relay started');

  const lines = [
    headline,
    '',
    'Doc ID:',
    id,
    '',
    `Paste in ${agentLabel}:`,
    clip,
  ];
  if (handoffUsesCliWatcher(normalized) && relayStatus === 'queued') {
    lines.push('', 'Optional: scripts/handoff-relay-watcher.ps1 -RunAgent');
  }

  uiModule?.showToast?.(lines.join('\n'), {
    duration: copied ? 25000 : 30000,
    ...(copied ? { leadingIcon: 'check' } : {}),
    toastClass: 'toast--handoff',
    action: external ? 'Open doc' : 'Open agent',
    onAction: () => {
      if (external) openHandoffDocument(id);
      else openHandoffAgentSession({ noteId, docId: id });
    },
  });
}

export function handoffUsesCliWatcher(target) {
  const t = normalizeHandoffTarget(target);
  return t === 'cursor' || t === 'claude';
}

export function handoffTargetIsExternal(target) {
  const t = normalizeHandoffTarget(target);
  return t === 'cursor' || t === 'claude' || t === 'hermes';
}

export function handoffStatusLabel(target, status) {
  const t = normalizeHandoffTarget(target);
  const external = handoffTargetIsExternal(t);
  switch (status) {
    case 'running':
      if (t === 'hermes') return 'Hermes running';
      return external ? 'CLI running' : 'Relay running';
    case 'queued':
      if (t === 'hermes') return 'Waiting for Hermes';
      return external ? 'Waiting for watcher' : 'Relay queued';
    case 'complete':
      return 'Complete';
    case 'failed':
      return 'Failed';
    default:
      return external ? 'Handoff saved' : 'Relay started';
  }
}

export function handoffChipTitle(target, status) {
  const t = normalizeHandoffTarget(target);
  const external = handoffTargetIsExternal(t);
  if (external && status === 'queued') {
    if (t === 'hermes') {
      return 'Hermes polls pending handoffs. Tap to open handoff doc.';
    }
    return 'Start scripts/handoff-relay-watcher.ps1 -RunAgent on your PC. Tap to open handoff doc.';
  }
  if (status === 'running') {
    if (t === 'hermes') return 'Hermes is working. Tap to open handoff doc.';
    return external ? 'Cursor/Claude CLI is working. Tap to open handoff doc.' : 'Odysseus relay is running. Tap to open handoff doc.';
  }
  if (status === 'complete') return 'Handoff complete — tap to read outcome in doc.';
  if (status === 'failed') return 'Handoff failed — tap to open doc for details.';
  return 'Handoff packet — tap to open';
}

function _dismissHandoffOverlays() {
  try { window.notesModule?.closePanel?.(); } catch {}
  try {
    const ab = window.agentBinModule;
    if (ab?.isAgentBinOpen?.()) ab.closeAgentBin();
  } catch {}
}

/** Close notes/agent-bin overlays, mount the doc pane, and open a handoff document. */
export async function openHandoffDocument(docId) {
  const id = String(docId || '').trim();
  if (!id) {
    uiModule?.showToast?.('No handoff document linked');
    return false;
  }
  const dm = window.documentModule;
  if (!dm?.loadDocument) {
    uiModule?.showError?.('Document editor not available');
    return false;
  }
  _dismissHandoffOverlays();
  try {
    if (dm.ensurePaneMounted) dm.ensurePaneMounted();
    else if (dm.openPanel) dm.openPanel();
    await dm.loadDocument(id);
    return true;
  } catch (err) {
    console.error('openHandoffDocument failed', err);
    uiModule?.showError?.('Could not open handoff document');
    return false;
  }
}

async function _fetchHandoffSessionId(noteId) {
  const nid = String(noteId || '').trim();
  if (!nid) return '';
  try {
    const res = await fetch(`${_API_BASE}/api/notes/${encodeURIComponent(nid)}`, {
      credentials: 'same-origin',
    });
    if (!res.ok) return '';
    const note = await res.json();
    return String(note.handoff_relay_session_id || note.agent_session_id || '').trim();
  } catch {
    return '';
  }
}

/** Switch to the relay agent session; falls back to the handoff doc while relay starts. */
export async function openHandoffAgentSession({ sessionId, noteId, docId } = {}) {
  let sid = String(sessionId || '').trim();
  if (!sid && noteId) sid = await _fetchHandoffSessionId(noteId);
  if (!sid && noteId) {
    await new Promise(r => setTimeout(r, 900));
    sid = await _fetchHandoffSessionId(noteId);
  }
  if (!sid) {
    if (docId) {
      uiModule?.showToast?.('Relay still starting — opening handoff doc');
      return openHandoffDocument(docId);
    }
    uiModule?.showToast?.('Agent session not ready yet — try again shortly');
    return false;
  }
  const sm = window.sessionModule;
  if (!sm?.selectSession) {
    uiModule?.showError?.('Sessions not available');
    return false;
  }
  _dismissHandoffOverlays();
  try {
    if (sm.loadSessions) await sm.loadSessions().catch(() => {});
    await sm.selectSession(sid);
    return true;
  } catch (err) {
    console.error('openHandoffAgentSession failed', err);
    uiModule?.showError?.('Could not open agent session');
    return false;
  }
}

/** Build a handoff payload from a text selection + inferred source metadata. */
export function buildHandoffPayloadFromSelection({ text, source } = {}) {
  const sessionMod = window.sessionModule;
  const sessionId = source?.sessionId || sessionMod?.getCurrentSessionId?.() || '';
  const sessions = sessionMod?.getSessions?.() || [];
  const session = sessions.find((s) => s.id === sessionId);
  const sessionName = session?.name || 'Untitled';

  const trimmed = String(text || '').trim();
  const firstLine = trimmed.split('\n').find((l) => l.trim()) || trimmed;
  const goal = firstLine.trim().slice(0, 120);
  const title = goal || 'Selection handoff';

  const context = [];
  if (source?.label) context.push(`Source: ${source.label}`);
  if (sessionId) context.push(`Odysseus session: ${sessionName} (${sessionId})`);
  context.push(`Selected at: ${new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')}`);

  const sourceHeader = source?.label ? `**From:** ${source.label}\n\n` : '';
  const noteBody = `${sourceHeader}\`\`\`\n${trimmed}\n\`\`\``;

  return { title, goal, context, noteBody, sessionId };
}

/** Target picker for selection handoffs — agents + web search agents. */
export function openHandoffTargetMenu(anchorRect, payload, { apiBase, selectionText, selectionSource } = {}) {
  document.querySelectorAll('.note-handoff-menu-dropdown.selection-handoff-menu').forEach((d) => d.remove());
  if (!payload) return;

  const searchText = selectionText || payload.goal || '';
  const searchSource = selectionSource || null;

  const menu = document.createElement('div');
  menu.className = 'note-corner-menu-dropdown note-handoff-menu-dropdown selection-handoff-menu';
  menu.innerHTML = `
    <div class="note-handoff-menu-label">Send to</div>
    <button type="button" class="ncm-item" data-target="cursor">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
      <span>Cursor</span>
    </button>
    <button type="button" class="ncm-item" data-target="claude">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>
      <span>Claude Code</span>
    </button>
    <button type="button" class="ncm-item" data-target="odysseus">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
      <span>Odysseus</span>
    </button>
    <button type="button" class="ncm-item" data-target="hermes">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M9 13h6"/><path d="M9 17h4"/></svg>
      <span>Hermes Agent : brudda</span>
    </button>
    <div class="selection-handoff-divider"></div>
    <div class="note-handoff-menu-label">Web search agents</div>
    <button type="button" class="ncm-item" data-search-agent="tinyfish">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 4a6 6 0 0 1 6 6c0 3-3 6-6 9-3-3-6-6-6-9a6 6 0 0 1 6-6Z"/><circle cx="12" cy="10" r="2" fill="currentColor" stroke="none"/></svg>
      <span>TinyFish</span>
    </button>
    <button type="button" class="ncm-item" data-search-agent="firecrawl">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <span>Firecrawl</span>
    </button>
    <button type="button" class="ncm-item" data-search-agent="perplexity">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <span>Perplexity</span>
    </button>
    <button type="button" class="ncm-item selection-handoff-more-search" data-action="more-search">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
      <span>More search agents…</span>
    </button>`;
  document.body.appendChild(menu);

  const r = anchorRect || { left: 8, top: 8, bottom: 40, right: 40 };
  const mw = 220;
  let left = Math.min(r.left, window.innerWidth - mw - 8);
  left = Math.max(8, left);
  const mh = menu.offsetHeight || 140;
  const below = window.innerHeight - r.bottom;
  let top = (below < mh + 8 && r.top > mh + 8) ? (r.top - mh - 4) : (r.bottom + 4);
  top = Math.max(8, Math.min(top, window.innerHeight - mh - 8));
  left = Math.max(8, Math.min(left, window.innerWidth - mw - 8));
  menu.style.cssText += `position:fixed;z-index:11000;top:${Math.round(top)}px;left:${Math.round(left)}px;`;

  const close = bindMenuDismiss(menu, () => menu.remove(), (ev) => {
    const bar = document.querySelector('.selection-action-bar');
    return !menu.contains(ev.target) && !(bar && bar.contains(ev.target));
  });

  menu.querySelectorAll('[data-target]').forEach((btn) => {
    btn.addEventListener('click', async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      close();
      try {
        const result = await createHandoffDocument({
          apiBase: apiBase || _API_BASE,
          target: btn.dataset.target,
          title: payload.title,
          goal: payload.goal,
          context: payload.context || [],
          noteBody: payload.noteBody || '',
          sessionId: payload.sessionId || '',
        });
        await notifyHandoffPickup({
          target: result.target,
          docId: result.docId,
          noteId: result.noteId,
          relayStatus: result.relayStatus,
        });
      } catch (err) {
        console.error('Selection handoff failed', err);
        uiModule?.showError?.(err?.message || 'Handoff failed');
      }
    });
  });

  menu.querySelectorAll('[data-search-agent]').forEach((btn) => {
    btn.addEventListener('click', async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      close();
      try {
        await runSelectionSearchAgent({
          provider: btn.dataset.searchAgent,
          text: searchText,
          source: searchSource,
        });
      } catch (err) {
        console.error('Selection search handoff failed', err);
        uiModule?.showError?.(err?.message || 'Search failed');
      }
    });
  });

  menu.querySelector('[data-action="more-search"]')?.addEventListener('click', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const rect = ev.currentTarget.getBoundingClientRect();
    close();
    openSearchAgentMenu(rect, { text: searchText, source: searchSource });
  });
}

export {
  HANDOFF_TITLE_PREFIX,
  HANDOFF_VALID_TARGETS,
};

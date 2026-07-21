/**
 * Parse chat/code-block text into a note payload and POST to /api/notes.
 * Used by code-block buttons and message footer "Save to Notes".
 */
import uiModule from './ui.js';

export const NOTE_BTN_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 3h12l4 4v14H4z"/><path d="M16 3v5h5"/></svg>';

function _firstLineTitle(text) {
  const line = (text.split('\n')[0] || '').replace(/^#+\s*/, '').trim();
  return line || null;
}

function _normalizeNoteBody(text) {
  return (text || '').replace(/\r\n/g, '\n').trim();
}

/** Drop trailing ## Links blocks that only point at internal #note- ids. */
function _stripInternalLinksSection(body) {
  const m = body.match(/\n## Links\s*\n([\s\S]*)$/i);
  if (!m) return body;
  const linkLines = m[1].trim().split('\n').filter(Boolean);
  if (!linkLines.length) return body.slice(0, m.index).trim();
  const onlyInternal = linkLines.every((l) =>
    /^(?:[-*]\s*)?(?:[\w\s./-]+:\s*)?#?note-[a-f0-9]+\s*$/i.test(l.trim()),
  );
  return onlyInternal ? body.slice(0, m.index).trim() : body;
}

function _cleanNoteMarkdown(content, title) {
  let body = _normalizeNoteBody(content);
  if (!body) return body;
  body = _stripInternalLinksSection(body);
  const t = (title || '').trim();
  if (t) {
    const h1 = body.match(/^#\s+(.+?)(?:\n|$)/);
    if (h1 && h1[1].trim().toLowerCase() === t.toLowerCase()) {
      body = body.slice(h1[0].length).trim();
    }
  }
  return body;
}

function _tryParseNoteJson(text) {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{')) return null;
  try {
    const obj = JSON.parse(trimmed);
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
    if (!('title' in obj || 'content' in obj || 'text' in obj || 'body' in obj || 'items' in obj || 'checklist_items' in obj)) {
      return null;
    }
    return obj;
  } catch {
    return null;
  }
}

function _notePayloadFromJson(obj, source) {
  const title = String(obj.title || '').trim();
  const itemsRaw = obj.checklist_items ?? obj.items;
  let items = null;
  if (Array.isArray(itemsRaw) && itemsRaw.length) {
    items = itemsRaw
      .map((it) => {
        if (typeof it === 'string') return { text: it.trim(), done: false };
        if (!it || typeof it !== 'object') return null;
        const text = String(it.text ?? it.label ?? '').trim();
        if (!text) return null;
        return { text, done: !!(it.done ?? it.checked) };
      })
      .filter(Boolean);
  }

  let content = obj.content != null ? String(obj.content) : '';
  if (!content && obj.text != null) content = String(obj.text);
  if (!content && obj.body != null) content = String(obj.body);
  content = _cleanNoteMarkdown(content, title);

  if (items?.length) {
    const payload = {
      title: (title || _firstLineTitle(content) || 'Checklist').slice(0, 200),
      note_type: 'checklist',
      items,
      source,
    };
    if (content) payload.content = content;
    if (obj.label) payload.label = String(obj.label);
    if (obj.due_date) payload.due_date = String(obj.due_date);
    return payload;
  }

  const body = content || _cleanNoteMarkdown(String(obj.text || obj.body || ''), title);
  const finalTitle = title || _firstLineTitle(body) || 'Note from chat';
  const payload = {
    title: finalTitle.slice(0, 200),
    content: body,
    note_type: obj.note_type === 'checklist' ? 'checklist' : 'note',
    source,
  };
  if (obj.label) payload.label = String(obj.label);
  if (obj.due_date) payload.due_date = String(obj.due_date);
  if (obj.color) payload.color = String(obj.color);
  return payload;
}

/** When a message wraps structured note data in a fenced block, prefer that inner text. */
export function extractNoteSourceText(raw) {
  const text = (raw || '').trim();
  if (!text) return '';
  const fenced = text.match(/```(?:json|txt|text|markdown|md)?\s*\n([\s\S]*?)```/i);
  if (fenced) {
    const inner = fenced[1].trim();
    if (inner.startsWith('{') || /^action:\s*add\b/i.test(inner)) return inner;
  }
  return text;
}

/** Turn chat/code-block text into a note payload for POST /api/notes. */
export function parseCodeBlockToNote(raw, source = 'chat_codeblock') {
  const text = extractNoteSourceText(raw);
  if (!text) return null;

  const jsonObj = _tryParseNoteJson(text);
  if (jsonObj) return _notePayloadFromJson(jsonObj, source);

  if (/^action:\s*add\b/i.test(text)) {
    const titleM = text.match(/\btitle:\s*(.*?)(?=\s+content:|\s+note_type:|\s+label:|\s+due_date:|$)/is);
    const contentM = text.match(/\bcontent:\s*([\s\S]*)$/i);
    const title = (titleM?.[1] || '').trim();
    const body = _cleanNoteMarkdown((contentM?.[1] || text).trim(), title);
    return {
      title: (title || _firstLineTitle(body) || 'Note from chat').slice(0, 200),
      content: body,
      note_type: 'note',
      source,
    };
  }

  const checklistRe = /^\s*[-*]\s*\[([ xX])\]\s+(.+)$/gm;
  const items = [];
  let m;
  while ((m = checklistRe.exec(text)) !== null) {
    items.push({ text: m[2].trim(), done: m[1].toLowerCase() === 'x' });
  }
  if (items.length) {
    const titleLines = text.split('\n').filter((l) => l.trim() && !/^\s*[-*]\s*\[([ xX])\]\s+/.test(l));
    const title = (titleLines[0] || '').replace(/^#+\s*/, '').trim() || 'Checklist';
    return {
      title: title.slice(0, 200),
      content: _stripInternalLinksSection(_normalizeNoteBody(text)),
      note_type: 'checklist',
      items,
      source,
    };
  }

  const heading = text.match(/^#{1,3}\s+(.+?)(?:\n([\s\S]*))?$/);
  if (heading) {
    const title = heading[1].trim();
    const body = _cleanNoteMarkdown(text, title);
    return {
      title: title.slice(0, 200),
      content: body,
      note_type: 'note',
      source,
    };
  }

  const firstLine = _firstLineTitle(text) || 'Note from chat';
  return {
    title: firstLine.slice(0, 200),
    content: _stripInternalLinksSection(_normalizeNoteBody(text)),
    note_type: 'note',
    source,
  };
}

export function codeBlockText(pre) {
  const codeEl = pre?.querySelector('code');
  if (codeEl) return (codeEl.textContent || '').trim();
  const copyBtn = pre?.querySelector('.copy-code');
  const fromAttr = copyBtn?.getAttribute('data-code');
  if (fromAttr) {
    const tmp = document.createElement('textarea');
    tmp.innerHTML = fromAttr;
    return (tmp.value || fromAttr).trim();
  }
  return (pre?.textContent || '').trim();
}

/**
 * Parse and POST a new note. Returns the saved note row or null.
 * @param {string} raw
 * @param {{ apiBase?: string, sessionId?: string, source?: string }} opts
 */
export async function saveNoteFromText(raw, opts = {}) {
  const source = opts.source || 'chat_codeblock';
  const payload = parseCodeBlockToNote(raw, source);
  if (!payload?.content && !payload?.items?.length) {
    uiModule?.showToast?.('Nothing to save');
    return null;
  }
  if (opts.sessionId) payload.session_id = opts.sessionId;

  const apiBase = opts.apiBase || window.location.origin;
  const res = await fetch(`${apiBase}/api/notes`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || 'Save failed');
  }
  const saved = await res.json();
  const label = (saved.title || payload.title || 'Note').slice(0, 60);
  uiModule?.showToast?.(`Note created: ${label}`);
  return saved;
}

function _htmlToPlainText(html) {
  if (!html) return '';
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || '').trim();
}

/** Build markdown note text from an email list row + optional full read payload. */
export function buildEmailNoteText(em, data = null, opts = {}) {
  const folder = opts.folder || 'INBOX';
  const subject = (data?.subject || em?.subject || '(no subject)').trim();
  const from = (data?.from_name || data?.from_address)
    ? `${data.from_name || ''}${data.from_address ? ` <${data.from_address}>` : ''}`.trim()
    : (em?.from_name || em?.from_address || em?.from || em?.sender || '').trim();
  const to = (data?.to || em?.to || '').trim();
  const cc = (data?.cc || em?.cc || '').trim();
  const dateRaw = data?.date || em?.date;
  const date = dateRaw ? new Date(dateRaw).toLocaleString() : '';
  const deepLink = `${window.location.origin}/#email=${encodeURIComponent(folder)}:${em?.uid}`;

  let body = (opts.readerBody || '').trim();
  if (!body && data) {
    if (data.body_text) body = String(data.body_text).trim();
    else if (data.body_html) body = _htmlToPlainText(data.body_html);
  }

  const lines = [
    `# ${subject}`,
    '',
    from ? `**From:** ${from}` : '',
    to ? `**To:** ${to}` : '',
    cc ? `**Cc:** ${cc}` : '',
    date ? `**Date:** ${date}` : '',
    `**Open:** ${deepLink}`,
    '',
    body,
  ].filter((line, idx, arr) => {
    if (line !== '') return true;
    return idx > 0 && arr[idx - 1] !== '';
  });

  return lines.join('\n').trim();
}

/**
 * Save an email as a note. Uses reader body when open; otherwise fetches /api/email/read.
 * @param {object} em — list-row email ({ uid, subject, from, … })
 * @param {{ reader?: Element, folder?: string, accountQuery?: string, emailData?: object, apiBase?: string }} opts
 */
export async function saveEmailToNote(em, opts = {}) {
  if (!em?.uid) {
    uiModule?.showToast?.('Nothing to save');
    return null;
  }
  const folder = opts.folder || 'INBOX';
  const apiBase = opts.apiBase || window.location.origin;
  const acct = opts.accountQuery || '';
  let data = opts.emailData || null;

  let readerBody = '';
  const reader = opts.reader;
  if (reader) {
    const bodyEl = reader.querySelector('.email-reader-body');
    if (bodyEl) readerBody = (bodyEl.innerText || bodyEl.textContent || '').trim();
  }

  if (!readerBody && !data) {
    const res = await fetch(
      `${apiBase}/api/email/read/${encodeURIComponent(em.uid)}?folder=${encodeURIComponent(folder)}${acct}`,
      { credentials: 'same-origin' },
    );
    if (!res.ok) throw new Error('Could not load email');
    data = await res.json();
    if (data?.error) throw new Error(data.error);
  }

  const raw = buildEmailNoteText(em, data, { folder, readerBody });
  const saved = await saveNoteFromText(raw, { apiBase, source: 'email' });
  return saved;
}

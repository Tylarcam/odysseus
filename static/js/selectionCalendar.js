/**
 * Selection → Calendar / scheduled tasks (planning docs, chat, notes).
 */

import uiModule from './ui.js';
import { bindMenuDismiss } from './escMenuStack.js';
import { openCalendarTo } from './calendar.js';
import {
  parseScheduleFromLine,
  previewScheduleItems,
  formatScheduleHint,
  toLocalIso,
  toDateOnly,
} from './scheduleParse.js';

const API_BASE = typeof window !== 'undefined' ? window.location.origin : '';

function _normalizePlanningLine(line) {
  return String(line || '')
    .replace(/^[\s*\-•]+/, '')
    .replace(/^\[[ xX]\]\s*/, '')
    .replace(/^step\s*\d+[:.)]\s*/i, '')
    .replace(/^#+\s*/, '')
    .replace(/^\d+[.)]\s*/, '')
    .trim();
}

export function splitPlanningItems(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];
  const lines = raw.split('\n').map(_normalizePlanningLine).filter(l => l.length >= 3);
  if (lines.length > 1) return lines;
  return [raw];
}

function _resolveItem(line) {
  const { title, start, timed } = parseScheduleFromLine(line);
  return {
    title: title || line.slice(0, 200),
    start,
    timed,
  };
}

function _sourceNote(source, fullText) {
  const label = source?.label || 'Selection';
  const clipped = String(fullText || '').trim().slice(0, 2000);
  return `From: ${label}${clipped ? `\n\n${clipped}` : ''}`;
}

function _schedulePreviewHtml(items) {
  const previews = previewScheduleItems(items);
  if (!previews.length) return '';

  const maxRows = 4;
  const rows = previews.slice(0, maxRows).map((p) => {
    const title = p.title.length > 42 ? `${p.title.slice(0, 39)}…` : p.title;
    const safeTitle = uiModule?.esc?.(title) ?? title;
    const safeWhen = uiModule?.esc?.(p.when) ?? p.when;
    return `<div class="selection-cal-preview-row"><span class="selection-cal-preview-when">${safeWhen}</span><span class="selection-cal-preview-title">${safeTitle}</span></div>`;
  });
  const more = previews.length > maxRows
    ? `<div class="selection-cal-preview-more">+${previews.length - maxRows} more</div>`
    : '';
  return `<div class="selection-cal-preview">${rows.join('')}${more}</div>`;
}

async function _postEvent(payload) {
  const res = await fetch(`${API_BASE}/api/calendar/events`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => '');
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

async function _postTask(payload) {
  const res = await fetch(`${API_BASE}/api/tasks`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function addSelectionAsEvents({ text, source } = {}) {
  const items = splitPlanningItems(text);
  if (!items.length) throw new Error('Nothing to schedule');
  const description = _sourceNote(source, text);
  let firstStart = null;
  let ok = 0;

  for (const line of items) {
    const { title, start, timed } = _resolveItem(line);
    if (!title) continue;
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    const payload = timed
      ? {
        summary: title,
        dtstart: toLocalIso(start),
        dtend: toLocalIso(end),
        all_day: false,
        description,
      }
      : {
        summary: title,
        dtstart: toDateOnly(start),
        dtend: toDateOnly(start),
        all_day: true,
        description,
      };
    await _postEvent(payload);
    if (!firstStart) firstStart = start;
    ok += 1;
  }

  return { count: ok, firstStart };
}

export async function addSelectionAsTasks({ text, source } = {}) {
  const items = splitPlanningItems(text);
  if (!items.length) throw new Error('Nothing to schedule');
  const context = _sourceNote(source, text);
  let firstStart = null;
  let ok = 0;

  for (const line of items) {
    const { title, start } = _resolveItem(line);
    if (!title) continue;
    const when = new Date(start);
    const pad2 = (n) => String(n).padStart(2, '0');
    await _postTask({
      name: title.slice(0, 120),
      prompt: `Planning item:\n${line}\n\n${context}`,
      task_type: 'llm',
      trigger_type: 'schedule',
      schedule: 'once',
      scheduled_date: when.toISOString(),
      scheduled_time: `${pad2(when.getHours())}:${pad2(when.getMinutes())}`,
    });
    if (!firstStart) firstStart = when;
    ok += 1;
  }

  return { count: ok, firstStart };
}

export function openCalTargetMenu(anchorRect, { text, source } = {}) {
  document.querySelectorAll('.selection-cal-menu-dropdown').forEach(d => d.remove());

  const items = splitPlanningItems(text);
  const countLabel = items.length > 1 ? ` (${items.length})` : '';
  const previewHtml = _schedulePreviewHtml(items);

  const menu = document.createElement('div');
  menu.className = 'note-corner-menu-dropdown note-handoff-menu-dropdown selection-cal-menu-dropdown';
  menu.innerHTML = `
    <div class="note-handoff-menu-label">Add to calendar</div>
    ${previewHtml}
    <button type="button" class="ncm-item" data-action="event">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      <span>Calendar event${countLabel}</span>
    </button>
    <button type="button" class="ncm-item" data-action="task">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      <span>Scheduled task${countLabel}</span>
    </button>`;

  const r = anchorRect || { left: 8, top: 8, bottom: 40, right: 40 };
  const mw = 280;
  let left = Math.min(r.left, window.innerWidth - mw - 8);
  left = Math.max(8, left);
  const mh = menu.offsetHeight || 160;
  const below = window.innerHeight - r.bottom;
  let top = (below < mh + 8 && r.top > mh + 8) ? (r.top - mh - 4) : (r.bottom + 4);
  top = Math.max(8, Math.min(top, window.innerHeight - mh - 8));
  menu.style.cssText += `position:fixed;z-index:11000;top:${Math.round(top)}px;left:${Math.round(left)}px;min-width:${mw}px;`;
  document.body.appendChild(menu);

  const close = bindMenuDismiss(menu, () => menu.remove(), (ev) => {
    const bar = document.querySelector('.selection-action-bar');
    return !menu.contains(ev.target) && !(bar && bar.contains(ev.target));
  });

  menu.querySelectorAll('[data-action]').forEach((btn) => {
    btn.addEventListener('click', async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      close();
      const action = btn.dataset.action;
      uiModule?.showToast?.('Scheduling…', { duration: 8000, leadingIcon: 'spinner' });
      try {
        let result;
        if (action === 'task') {
          result = await addSelectionAsTasks({ text, source });
          uiModule?.showToast?.(
            result.count > 1
              ? `${result.count} scheduled tasks created`
              : 'Scheduled task created',
            {
              duration: 8000,
              action: 'Open tasks',
              onAction: () => window.tasksModule?.openTasks?.(),
            },
          );
        } else {
          result = await addSelectionAsEvents({ text, source });
          const whenHint = result.firstStart ? formatScheduleHint(result.firstStart) : '';
          uiModule?.showToast?.(
            result.count > 1
              ? `${result.count} calendar events created`
              : (whenHint ? `Event · ${whenHint}` : 'Calendar event created'),
            {
              duration: 8000,
              action: 'Open calendar',
              onAction: () => {
                if (result.firstStart) openCalendarTo(toDateOnly(result.firstStart));
                else openCalendarTo();
              },
            },
          );
        }
      } catch (err) {
        console.error('Selection calendar failed', err);
        uiModule?.showError?.(err?.message || 'Failed to schedule');
      }
    });
  });
}

export default {
  openCalTargetMenu,
  addSelectionAsEvents,
  addSelectionAsTasks,
  splitPlanningItems,
  parseScheduleFromLine,
};

/**
 * Natural-language date/time parsing for calendar events and scheduled tasks.
 * Finds date and time tokens anywhere in a line (not only at the prefix).
 *
 * Rules:
 * - Time only → today at that time
 * - Date only → that day at 9:00
 * - Neither → today at 9:00
 * - Explicit date tokens (today, tomorrow, weekday, YYYY-MM-DD, etc.) win over defaults
 */

function _pad2(n) {
  return String(n).padStart(2, '0');
}

export function startOfToday(now = new Date()) {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d;
}

export function applyClock(baseDate, hh, mm) {
  const d = new Date(baseDate);
  d.setHours(hh, mm, 0, 0);
  return d;
}

function _parseClock(hh, mm, mer) {
  let h = parseInt(hh, 10);
  const m = mm != null && mm !== '' ? parseInt(mm, 10) : 0;
  const merL = (mer || '').toLowerCase();
  if (merL === 'pm' && h < 12) h += 12;
  if (merL === 'am' && h === 12) h = 0;
  if (h > 23 || m > 59) return null;
  return { h, m };
}

const _WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const _MONTHS = {
  jan: 0, january: 0, feb: 1, february: 1, mar: 2, march: 2, apr: 3, april: 3,
  may: 4, jun: 5, june: 5, jul: 6, july: 6, aug: 7, august: 7,
  sep: 8, sept: 8, september: 8, oct: 9, october: 9, nov: 10, november: 10, dec: 11, december: 11,
};

/** Remove matched spans (descending index) and tidy punctuation. */
function _titleWithoutSpans(text, spans) {
  let t = text;
  for (const { start, end } of [...spans].sort((a, b) => b.start - a.start)) {
    t = t.slice(0, start) + ' ' + t.slice(end);
  }
  return t
    .replace(/\(\s*\)/g, '')
    .replace(/\s+([,.;:])/g, '$1')
    .replace(/([,.;:])\s*([,.;:])+/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .replace(/^[\s,.:;\-–—]+|[\s,.:;\-–—]+$/g, '')
    .trim();
}

/**
 * Find an explicit calendar day anywhere in the line.
 * @returns {{ date: Date, spans: {start,end}[], hasExplicitDate: boolean, relative?: boolean } | null}
 */
function _extractDateAnchor(s, now = new Date()) {
  const spans = [];

  let m = s.match(/\bin\s+(\d+)\s*(m|min|mins|minutes|h|hr|hrs|hours|d|day|days)\b/i);
  if (m) {
    const n = parseInt(m[1], 10);
    const unit = m[2].toLowerCase();
    const d = new Date(now);
    if (unit.startsWith('m')) d.setMinutes(d.getMinutes() + n);
    else if (unit.startsWith('h')) d.setHours(d.getHours() + n);
    else d.setDate(d.getDate() + n);
    spans.push({ start: m.index, end: m.index + m[0].length });
    return { date: d, spans, hasExplicitDate: true, relative: true };
  }

  m = s.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
  if (m) {
    const d = new Date(+m[1], +m[2] - 1, +m[3], 0, 0, 0, 0);
    spans.push({ start: m.index, end: m.index + m[0].length });
    return { date: d, spans, hasExplicitDate: true };
  }

  m = s.match(/\b(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\b/);
  if (m) {
    let y = m[3] ? parseInt(m[3], 10) : now.getFullYear();
    if (y < 100) y += 2000;
    const d = new Date(y, +m[1] - 1, +m[2], 0, 0, 0, 0);
    spans.push({ start: m.index, end: m.index + m[0].length });
    return { date: d, spans, hasExplicitDate: true };
  }

  m = s.match(/\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b/i);
  if (m) {
    const month = _MONTHS[m[1].toLowerCase().replace(/\.$/, '')];
    const day = parseInt(m[2], 10);
    const y = m[3] ? parseInt(m[3], 10) : now.getFullYear();
    const d = new Date(y, month, day, 0, 0, 0, 0);
    spans.push({ start: m.index, end: m.index + m[0].length });
    return { date: d, spans, hasExplicitDate: true };
  }

  m = s.match(/\b(today|tomorrow)\b/i);
  if (m) {
    const d = startOfToday(now);
    if (m[1].toLowerCase() === 'tomorrow') d.setDate(d.getDate() + 1);
    spans.push({ start: m.index, end: m.index + m[0].length });
    return { date: d, spans, hasExplicitDate: true };
  }

  m = s.match(/\b(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i);
  if (m) {
    const target = _WEEKDAYS.indexOf(m[1].toLowerCase());
    const d = startOfToday(now);
    const cur = d.getDay();
    let delta = (target - cur + 7) % 7;
    d.setDate(d.getDate() + delta);
    spans.push({ start: m.index, end: m.index + m[0].length });
    return { date: d, spans, hasExplicitDate: true };
  }

  return null;
}

/**
 * Find a clock time anywhere in the line.
 * @returns {{ h: number, m: number, spans: {start,end}[] } | null}
 */
function _extractTime(s) {
  let m = s.match(/\b(?:@|at\s+)?(\d{1,2})(?::(\d{2}))?\s*(a\.?\s*m\.?|p\.?\s*m\.?)\b/i);
  if (m) {
    const mer = /p/i.test(m[3]) ? 'pm' : 'am';
    const clock = _parseClock(m[1], m[2], mer);
    if (!clock) return null;
    return { ...clock, spans: [{ start: m.index, end: m.index + m[0].length }] };
  }

  m = s.match(/\b(?:@|at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b/);
  if (m) {
    const clock = _parseClock(m[1], m[2], null);
    if (!clock) return null;
    return { ...clock, spans: [{ start: m.index, end: m.index + m[0].length }] };
  }

  return null;
}

/**
 * Parse date/time from anywhere in a planning line.
 * @returns {{ title: string, start: Date, timed: boolean, hasExplicitDate: boolean }}
 */
export function parseScheduleFromLine(line, now = new Date()) {
  const raw = String(line || '').trim();
  if (!raw) {
    return { title: '', start: applyClock(startOfToday(now), 9, 0), timed: true, hasExplicitDate: false };
  }

  const dateAnchor = _extractDateAnchor(raw, now);
  const timePart = _extractTime(raw);
  const allSpans = [
    ...(dateAnchor?.spans || []),
    ...(timePart?.spans || []),
  ];

  const baseDay = dateAnchor?.date || startOfToday(now);
  const hasExplicitDate = !!dateAnchor?.hasExplicitDate;

  if (timePart) {
    const start = applyClock(baseDay, timePart.h, timePart.m);
    const title = _titleWithoutSpans(raw, allSpans) || raw;
    return { title: title.slice(0, 200), start, timed: true, hasExplicitDate };
  }

  if (dateAnchor) {
    if (dateAnchor.relative) {
      const title = _titleWithoutSpans(raw, allSpans) || raw;
      return { title: title.slice(0, 200), start: dateAnchor.date, timed: true, hasExplicitDate: true };
    }
    const title = _titleWithoutSpans(raw, allSpans) || raw;
    return {
      title: title.slice(0, 200),
      start: applyClock(baseDay, 9, 0),
      timed: true,
      hasExplicitDate: true,
    };
  }

  return {
    title: raw.slice(0, 200),
    start: applyClock(startOfToday(now), 9, 0),
    timed: true,
    hasExplicitDate: false,
  };
}

/** Human-readable schedule hint for menus and toasts. */
export function formatScheduleHint(start, locale = undefined) {
  if (!(start instanceof Date) || Number.isNaN(start.getTime())) return '';
  return start.toLocaleString(locale, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/** Preview multiple planning lines for the Cal menu. */
export function previewScheduleItems(lines, now = new Date()) {
  return lines.map((line) => {
    const { title, start } = parseScheduleFromLine(line, now);
    return {
      line,
      title: title || line.slice(0, 200),
      when: formatScheduleHint(start),
      start,
    };
  });
}

export function toLocalIso(d) {
  return `${d.getFullYear()}-${_pad2(d.getMonth() + 1)}-${_pad2(d.getDate())}T${_pad2(d.getHours())}:${_pad2(d.getMinutes())}:00`;
}

export function toDateOnly(d) {
  return `${d.getFullYear()}-${_pad2(d.getMonth() + 1)}-${_pad2(d.getDate())}`;
}

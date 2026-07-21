/**
 * Send JD content through the job search pipeline (ingest + auto_process).
 */

function _parseJobPipelineError(res, data, fallback) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || d).join('; ');
  return data?.error || fallback;
}

export async function runJobPipelineFromEmail(em, opts = {}) {
  if (!em?.uid) {
    const { showToast } = await import('./ui.js');
    showToast?.('Nothing to process');
    return null;
  }

  const folder = opts.folder || 'INBOX';
  const apiBase = opts.apiBase || window.location.origin;
  const acct = opts.accountQuery || '';
  let subject = (em.subject || '').trim();
  let body = (opts.body || '').trim();
  let messageId = em.message_id || null;

  if (!body && opts.reader) {
    const bodyEl = opts.reader.querySelector('.email-reader-body');
    if (bodyEl) {
      body = (bodyEl.innerText || bodyEl.textContent || '').trim();
    }
  }

  if (!body) {
    const res = await fetch(
      `${apiBase}/api/email/read/${encodeURIComponent(em.uid)}?folder=${encodeURIComponent(folder)}${acct}`,
      { credentials: 'same-origin' },
    );
    if (!res.ok) throw new Error('Could not load email');
    const emailData = await res.json();
    if (emailData?.error) throw new Error(emailData.error);
    subject = (emailData.subject || subject).trim();
    body = (emailData.body || '').trim();
    messageId = emailData.message_id || messageId;
  }

  const { showToast } = await import('./ui.js');
  showToast?.('Starting job pipeline…');

  const res = await fetch(`${apiBase}/api/jobs/ingest-from-email`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      uid: String(em.uid),
      folder,
      subject,
      body,
      message_id: messageId,
      auto_process: opts.autoProcess !== false,
    }),
  });

  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }

  if (!res.ok) {
    throw new Error(_parseJobPipelineError(res, data, 'Job pipeline failed'));
  }

  const job = data.job || {};
  const status = job.status || 'started';
  const parts = [job.company, job.role].filter(Boolean);
  const label = parts.length ? parts.join(' — ') : (subject || 'Job');
  showToast?.(`Pipeline: ${label} (${status})`);
  return job;
}

export async function runJobPipelineFromDocument(doc, opts = {}) {
  if (!doc?.id) {
    const { showToast } = await import('./ui.js');
    showToast?.('Nothing to process');
    return null;
  }

  const apiBase = opts.apiBase || window.location.origin;
  const { showToast } = await import('./ui.js');
  showToast?.('Starting job pipeline…');

  const res = await fetch(`${apiBase}/api/jobs/ingest-from-document`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      doc_id: String(doc.id),
      auto_process: opts.autoProcess !== false,
    }),
  });

  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }

  if (!res.ok) {
    throw new Error(_parseJobPipelineError(res, data, 'Job pipeline failed'));
  }

  const job = data.job || {};
  const status = job.status || 'started';
  const parts = [job.company, job.role].filter(Boolean);
  const label = parts.length ? parts.join(' — ') : (doc.title || 'Job');
  showToast?.(`Pipeline: ${label} (${status})`);
  return job;
}

export const JOB_PIPELINE_BTN_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>';

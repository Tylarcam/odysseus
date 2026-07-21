/**
 * Job attention panel — opened from V.A.U.L.T. Agency branch / hero.
 */

function _esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

let _panel = null;
let _jobsDetail = {};

function _ensureStyles() {
  if (document.getElementById('cmd-jobs-styles')) return;
  const style = document.createElement('style');
  style.id = 'cmd-jobs-styles';
  style.textContent = `
#cmd-jobs-panel {
  position: fixed; inset: 0; z-index: 9300;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.65);
  font-family: "JetBrains Mono", ui-monospace, monospace;
}
#cmd-jobs-panel.hidden { display: none; }
.cmd-jobs-card {
  width: min(520px, 92vw); max-height: 80vh; overflow: auto;
  background: #080f08; border: 1px solid rgba(166,226,46,0.28);
  box-shadow: 0 0 24px rgba(166,226,46,0.12);
  color: #a6e22e;
}
.cmd-jobs-h {
  padding: 12px 14px; border-bottom: 1px solid rgba(166,226,46,0.18);
  font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase;
  display: flex; align-items: center; justify-content: space-between;
}
.cmd-jobs-close {
  border: 1px solid rgba(166,226,46,0.3); background: transparent; color: #a6e22e;
  width: 26px; height: 26px; cursor: pointer; font-size: 16px; line-height: 1;
}
.cmd-jobs-section { padding: 10px 14px; }
.cmd-jobs-section h5 {
  margin: 0 0 8px; font-size: 9px; letter-spacing: 0.22em; opacity: 0.65;
  text-transform: uppercase;
}
.cmd-jobs-row {
  padding: 8px 0; border-bottom: 1px solid rgba(166,226,46,0.08);
  font-size: 11px;
}
.cmd-jobs-row strong { color: #7fff00; font-weight: 600; }
.cmd-jobs-empty { opacity: 0.5; font-size: 10px; padding: 8px 0; }
.cmd-jobs-actions { display: flex; gap: 6px; margin-top: 6px; }
.cmd-jobs-btn {
  border: 1px solid rgba(166,226,46,0.3); background: transparent; color: #a6e22e;
  font-family: inherit; font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 4px 8px; cursor: pointer;
}
.cmd-jobs-btn:hover { background: rgba(166,226,46,0.12); color: #7fff00; }
.cmd-jobs-btn:disabled { opacity: 0.35; cursor: default; }
.cmd-jobs-detail {
  margin-top: 6px; padding: 8px; border: 1px solid rgba(166,226,46,0.15);
  background: rgba(166,226,46,0.04); font-size: 10px; opacity: 0.85;
  white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow: auto;
}
`;
  document.head.appendChild(style);
}

function _jobRow(job, { showApply, showApplied } = {}) {
  const id = _esc(job.id || '');
  return `
    <div class="cmd-jobs-row" data-job-id="${id}">
      <strong>${_esc(job.company || 'Company')}</strong> — ${_esc(job.role || 'Role')}
      <div style="opacity:0.55;font-size:9px;margin-top:2px;">${_esc(job.status || '')}</div>
      <div class="cmd-jobs-actions">
        <button type="button" class="cmd-jobs-btn" data-job-action="open" data-job-id="${id}">Open</button>
        ${showApply ? `<button type="button" class="cmd-jobs-btn" data-job-action="apply-package" data-job-id="${id}">Apply package</button>` : ''}
        ${showApplied ? `<button type="button" class="cmd-jobs-btn" data-job-action="mark-applied" data-job-id="${id}" ${job.status === 'applied' ? 'disabled' : ''}>${job.status === 'applied' ? 'Applied' : 'Mark applied'}</button>` : ''}
      </div>
      <div class="cmd-jobs-detail" id="cmd-jobs-detail-${id}" style="display:none;"></div>
    </div>`;
}

export function openJobAttentionPanel(jobsDetail = {}) {
  _ensureStyles();
  _jobsDetail = jobsDetail || {};
  const ready = _jobsDetail.ready_to_apply || [];
  const review = _jobsDetail.needs_review || [];
  const headline = _jobsDetail.headline || 'Job pipeline';

  if (!_panel) {
    _panel = document.createElement('div');
    _panel.id = 'cmd-jobs-panel';
    document.body.appendChild(_panel);
    _panel.addEventListener('click', (e) => {
      if (e.target === _panel) closeJobAttentionPanel();
    });
    _panel.addEventListener('click', _onRowActionClick);
  }

  const readyHtml = ready.length
    ? ready.map((j) => _jobRow(j, { showApply: true, showApplied: true })).join('')
    : '<div class="cmd-jobs-empty">Nothing ready to apply</div>';

  const reviewHtml = review.length
    ? review.map((j) => _jobRow(j, { showApply: false, showApplied: false })).join('')
    : '<div class="cmd-jobs-empty">Nothing needs review</div>';

  _panel.innerHTML = `
    <div class="cmd-jobs-card" role="dialog" aria-label="Job attention">
      <div class="cmd-jobs-h">
        <span>${_esc(headline)}</span>
        <button type="button" class="cmd-jobs-close" id="cmd-jobs-close" aria-label="Close">×</button>
      </div>
      <div class="cmd-jobs-section">
        <h5>Ready to apply (${ready.length})</h5>
        ${readyHtml}
      </div>
      <div class="cmd-jobs-section">
        <h5>Needs review (${review.length})</h5>
        ${reviewHtml}
      </div>
    </div>
  `;
  _panel.classList.remove('hidden');
  document.getElementById('cmd-jobs-close')?.addEventListener('click', closeJobAttentionPanel);
}

export function closeJobAttentionPanel() {
  _panel?.classList.add('hidden');
}

function _findJob(jobId) {
  const all = [...(_jobsDetail.ready_to_apply || []), ...(_jobsDetail.needs_review || [])];
  return all.find((j) => String(j.id) === String(jobId));
}

async function _onRowActionClick(e) {
  const btn = e.target.closest('[data-job-action]');
  if (!btn) return;
  e.preventDefault();
  const jobId = btn.dataset.jobId;
  const action = btn.dataset.jobAction;
  if (!jobId || !action) return;

  const { showToast } = await import('./ui.js');
  const detailEl = document.getElementById(`cmd-jobs-detail-${jobId}`);

  if (action === 'open') {
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || 'Job not found');
      if (detailEl) {
        const job = data.job || {};
        detailEl.textContent = JSON.stringify(
          {
            status: job.status,
            company: job.company,
            role: job.role,
            location: job.location,
            match_score: job.match_score,
            gate_score: job.gate_score,
            apply_url: job.apply_url,
          },
          null,
          2,
        );
        detailEl.style.display = detailEl.style.display === 'none' ? 'block' : 'none';
      }
    } catch (err) {
      showToast?.(err.message || 'Failed to open job');
    }
    return;
  }

  if (action === 'apply-package') {
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/apply-package`, { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || 'Apply package not available');
      if (detailEl) {
        detailEl.textContent = JSON.stringify(data.apply_package || {}, null, 2);
        detailEl.style.display = 'block';
      }
    } catch (err) {
      showToast?.(err.message || 'Failed to load apply package');
    }
    return;
  }

  if (action === 'mark-applied') {
    try {
      btn.disabled = true;
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/mark-applied`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      const raw = await res.text();
      let data = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        if (!res.ok) throw new Error(raw?.slice(0, 120) || `Mark applied failed (${res.status})`);
        throw new Error('Mark applied returned invalid JSON');
      }
      if (!res.ok) throw new Error(data?.detail || data?.error || `Mark applied failed (${res.status})`);
      showToast?.('Marked applied');
      btn.textContent = 'Applied';
      const job = _findJob(jobId);
      if (job) job.status = 'applied';
    } catch (err) {
      btn.disabled = false;
      showToast?.(err.message || 'Failed to mark applied');
    }
    return;
  }
}

export default { openJobAttentionPanel, closeJobAttentionPanel };

/**
 * Selection → Generate Prompt (client-side, template-based draft).
 *
 * Deterministic fill of a structured prompt template from the highlighted
 * text — no backend call, no LLM. Anything not derivable from the selection
 * alone (role, constraints, deliverables, format) is left as an explicit
 * [NEEDED: ...] placeholder rather than invented.
 */

import uiModule from './ui.js';
import { bindMenuDismiss } from './escMenuStack.js';

function _contextLine(source) {
  const label = source?.label || 'Selection';
  return `Source: ${label}`;
}

export function buildPromptDraft(text, source) {
  const objective = String(text || '').trim();
  const quoted = objective
    ? objective.split('\n').map((l) => `> ${l}`).join('\n')
    : '[NEEDED: source material or reference to work from]';

  return `# Role
Act as a [NEEDED: subject-matter expert best suited to this request].

# Objective
${objective || '[NEEDED: describe the desired outcome]'}

# Context
${_contextLine(source)}

# Inputs
Use the following inputs:
${quoted}

If required information is missing, do not fabricate it. Use clearly labeled
placeholders in this form: [NEEDED: description].

# Task
1. Analyze the request and identify the intended outcome.
2. Produce the requested work using the context and constraints below.
3. State assumptions separately from verified facts.
4. Handle important edge cases and trade-offs.
5. Perform a final quality review before responding.

# Constraints
[NEEDED: exclusions, time/budget/tech limits, safety, or style requirements]

# Deliverables
Provide:
[NEEDED: exact output(s) expected]

# Required Format
Return the result as [NEEDED: markdown, JSON, HTML, table, code, or another format].

# Quality Bar
The response must:
- Preserve all stated constraints.
- Be specific, actionable, and internally consistent.
- Avoid unsupported claims or invented details.
- Identify uncertainty where it materially affects the result.
- Include validation steps, acceptance criteria, or evidence where applicable.

# Final Self-Check
Before finalizing, verify that:
1. Every explicit requirement is addressed.
2. No facts were invented.
3. The output format matches the requested format.
4. Assumptions and unresolved questions are labeled.
5. The result is usable without additional interpretation.`;
}

function _livePromptText(pre, fallback = '') {
  const codeEl = pre?.querySelector('code');
  if (codeEl) return (codeEl.textContent || '').trim() || fallback;
  return (pre?.textContent || '').trim() || fallback;
}

export function openGenTargetMenu(anchorRect, { text, source } = {}) {
  document.querySelectorAll('.selection-gen-menu-dropdown').forEach((d) => d.remove());

  const draft = buildPromptDraft(text, source);

  const menu = document.createElement('div');
  menu.className = 'note-corner-menu-dropdown selection-gen-menu-dropdown';
  // Wrap draft in <code> so chat's global .edit-code / .copy-code / .save-to-note
  // controls (injected by MutationObserver) can edit and sync like chat blocks.
  menu.innerHTML = `
    <div class="note-handoff-menu-label">Generate Prompt</div>
    <pre class="selection-gen-preview"><code></code></pre>
    <button type="button" class="ncm-item selection-gen-copy-btn" data-action="copy">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      <span>Copy prompt</span>
    </button>`;
  const pre = menu.querySelector('.selection-gen-preview');
  const codeEl = pre.querySelector('code');
  codeEl.textContent = draft;

  const r = anchorRect || { left: 8, top: 8, bottom: 40, right: 40 };
  const mw = 320;
  let left = Math.min(r.left, window.innerWidth - mw - 8);
  left = Math.max(8, left);
  const mh = menu.offsetHeight || 320;
  const below = window.innerHeight - r.bottom;
  let top = (below < mh + 8 && r.top > mh + 8) ? (r.top - mh - 4) : (r.bottom + 4);
  top = Math.max(8, Math.min(top, window.innerHeight - mh - 8));
  menu.style.cssText += `position:fixed;z-index:11000;top:${Math.round(top)}px;left:${Math.round(left)}px;min-width:${mw}px;`;
  document.body.appendChild(menu);

  bindMenuDismiss(menu, () => menu.remove(), (ev) => {
    const bar = document.querySelector('.selection-action-bar');
    return !menu.contains(ev.target) && !(bar && bar.contains(ev.target));
  });

  menu.querySelector('[data-action="copy"]').addEventListener('click', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    // Prefer live <code> text so edits (via the pencil) are what get copied.
    uiModule?.copyToClipboard?.(_livePromptText(pre, draft));
  });

  return menu;
}

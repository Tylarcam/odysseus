/** Shared helper: start Clicky worker + WPF overlay via Odysseus API.
 * DISABLED in UI (CMD Center + /clicky): Docker Odysseus runs Linux and cannot spawn
 * the Windows WPF app via POST /api/clicky/start. Use deploy/scripts/start-clicky.ps1 on the host.
 */

export async function launchClicky(apiBase, { launchApp = true } = {}) {
  const base = (apiBase || window.location.origin || '').replace(/\/$/, '');
  const res = await fetch(`${base}/api/clicky/start`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ launch_app: launchApp }),
  });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  if (!res.ok) {
    const detail = data.detail || data.error || data.message || `HTTP ${res.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

export function clickyLaunchToast(data, showToast) {
  if (!showToast) return;
  const model = data?.worker_health?.chat_model;
  const suffix = model ? ` (${model})` : '';
  showToast((data?.message || 'Clicky launched') + suffix, 4500);
}

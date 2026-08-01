/**
 * V.A.U.L.T. — Branch constellation (2D canvas sphere network).
 * Knowledge-graph data nodes overlay live Odysseus + MemPalace entities.
 */

const STAR_COUNT = 120;
const LAT_STEPS = 18;
const LON_STEPS = 34;
const EXTRA_NODES = 90;
const DRAG_THRESHOLD_PX = 5;
const DRAG_SENSITIVITY = 0.005;

const ZOOM_MIN = 0.55;
const ZOOM_MAX = 2.4;
const ZOOM_STEP = 1.0015;

// Data-node kinds that open the retro terminal popup instead of navigating.
const POPUP_KINDS = new Set(['project', 'agent', 'urgent', 'scheduled']);

// Kind/branch → terminal header label (caps, spaced).
function _popupHeader(node) {
  const k = node.kind;
  if (k === 'project') return 'PROJECT';
  if (k === 'agent') return 'AGENT ACTIVITY';
  if (k === 'scheduled') return 'SCHEDULED';
  if (k === 'urgent') {
    const b = node.branch || '';
    if (b === 'relay') return 'AGENT RELAY';
    if (b === 'agency') return 'JOB LEAD';
    if (b === 'prod') return (node.summary || '').startsWith('Due') ? 'DUE NOTE' : 'URGENT';
    return 'URGENT';
  }
  return String(k || 'NODE').toUpperCase();
}

/** Branch markers on the globe surface (phi, theta radians). */
const BRANCH_SPHERE = {
  core: { phi: Math.PI * 0.48, theta: 0, size: 5.5 },
  mem: { phi: Math.PI * 0.32, theta: 0.65, size: 3.8 },
  prod: { phi: Math.PI * 0.32, theta: 2.05, size: 3.8 },
  intel: { phi: Math.PI * 0.32, theta: 3.45, size: 3.8 },
  comms: { phi: Math.PI * 0.32, theta: 4.85, size: 3.8 },
  agency: { phi: Math.PI * 0.64, theta: 0.95, size: 4.2 },
  relay: { phi: Math.PI * 0.64, theta: 2.75, size: 4.2 },
  voice: { phi: Math.PI * 0.64, theta: 4.55, size: 3.6 },
  mycelia: { phi: Math.PI * 0.50, theta: 1.55, size: 3.6 },
};

const STATE_RGB = {
  online: { fill: '238,255,241', glow: '198,255,205' },
  alive: { fill: '238,255,241', glow: '198,255,205' },
  busy: { fill: '255,210,210', glow: '255,107,107' },
  idle: { fill: '120,255,145', glow: '120,255,145' },
};

const NODE_TONES = {
  bright: { fill: '238,255,241', glow: '198,255,205', alpha: 0.95 },
  urgent: { fill: '255,92,73', glow: '255,92,73', alpha: 0.95 },
  scheduled: { fill: '255,179,71', glow: '255,179,71', alpha: 0.92 },
  agent: { fill: '255,210,80', glow: '255,230,120', alpha: 0.9 },
  memory: { fill: '120,220,255', glow: '80,200,240', alpha: 0.82 },
  idle: { fill: '120,255,145', glow: '120,255,145', alpha: 0.6 },
};

/** Attention triad (calm / due / overdue) — drives status encoding on data nodes. */
const ATTENTION = {
  calm: {
    fill: '120,255,145',
    glow: '120,255,145',
    hex: '#78ff91',
    label: 'CALM',
    alpha: 0.88,
    sizeMul: 1.0,
    glowBlur: 12,
  },
  due: {
    fill: '255,179,71',
    glow: '255,179,71',
    hex: '#ffb347',
    label: 'DUE SOON',
    alpha: 0.92,
    sizeMul: 1.14,
    glowBlur: 17,
  },
  overdue: {
    fill: '255,92,73',
    glow: '255,92,73',
    hex: '#ff5c49',
    label: 'OVERDUE',
    alpha: 0.95,
    sizeMul: 1.26,
    glowBlur: 22,
  },
};

const HIGHLIGHT_MS_DEFAULT = 3000;
const HIGHLIGHT_MS_MIN = 2000;
const HIGHLIGHT_MS_MAX = 4000;

let _canvas = null;
let _ctx = null;
let _mount = null;
let _frame = null;
let _paused = false;
let _resizeObserver = null;
let _onNodeClick = null;
let _inProgress = 0;
let _tooltip = null;
let _legend = null;
let _highlight = { ids: null, branch: null, status: null, until: 0 };

let _w = 0;
let _h = 0;
let _cx = 0;
let _cy = 0;
let _globeRadius = 0;

let _sphereNodes = [];
let _stars = [];
let _branches = {};
let _particles = [];
let _branchHealth = [];
let _dataNodes = [];
let _dataEdges = [];
let _nodeById = {};
let _cardAnchors = [];

let _userRotX = 0;
let _userRotY = 0;
let _autoSpin = true;
let _viewScale = 1;
let _prefersReducedMotion = false;
let _isNarrow = false;
let _drag = { active: false, moved: false, startX: 0, startY: 0, lastX: 0, lastY: 0 };
const _activePointers = new Map();
let _pinch = { active: false, startDist: 0, startScale: 1 };
let _popup = null;
let _popupNode = null;
let _onPopupOpen = null;
let _dismissBinding = null;

function _stableHash(text) {
  let h = 0;
  const s = String(text || '');
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

function _stateRgb(state) {
  return STATE_RGB[state] || STATE_RGB.idle;
}

function _toneRgb(tone) {
  return NODE_TONES[tone] || NODE_TONES.idle;
}

/**
 * Resolve calm|due|overdue for status encoding.
 * Prefers explicit node.status / tone; falls back to kind (urgent→overdue).
 * Agent run statuses (running/idle/…) are ignored so they keep specialty tones.
 */
function _attentionStatus(node) {
  if (!node) return null;
  const raw = String(node.status || '').toLowerCase();
  if (raw === 'calm') return 'calm';
  if (raw === 'due' || raw === 'soon') return 'due';
  if (raw === 'overdue' || raw === 'urgent') return 'overdue';

  const tone = String(node.tone || '').toLowerCase();
  if (tone === 'urgent') return 'overdue';
  if (tone === 'scheduled') return 'due';
  // Explicit calm only — do not coerce specialty tones (bright/agent/memory).
  if (tone === 'calm') return 'calm';

  const kind = String(node.kind || '').toLowerCase();
  if (kind === 'urgent') return 'overdue';
  if (kind === 'scheduled') return 'due';
  return null;
}

function _attentionStyle(node) {
  const key = _attentionStatus(node);
  return key ? ATTENTION[key] : null;
}

function _statusChipText(node) {
  const attn = _attentionStatus(node);
  if (node?.due_label) return String(node.due_label).toUpperCase();
  if (attn) return ATTENTION[attn].label;
  return '';
}

function _ctaLabel(node) {
  const attn = _attentionStatus(node);
  if (attn === 'overdue') return 'RESOLVE \u25B6';
  if (attn === 'due') return 'REVIEW \u25B6';
  if (node?.kind === 'agent') return 'OPEN RUN \u25B6';
  if (node?.kind === 'project') return 'OPEN PROJECT \u25B6';
  if (node?.kind === 'scheduled') return 'OPEN \u25B6';
  return 'OPEN \u25B6';
}

function _nodeMatchesHighlight(node) {
  if (!_highlight.until || performance.now() > _highlight.until) return false;
  const hasIds = _highlight.ids && _highlight.ids.size > 0;
  const hasBranch = !!_highlight.branch;
  const hasStatus = !!_highlight.status;
  if (!hasIds && !hasBranch && !hasStatus) return false;
  if (hasIds && !_highlight.ids.has(String(node.id))) return false;
  if (hasBranch && node.branch !== _highlight.branch) return false;
  if (hasStatus) {
    const attn = _attentionStatus(node);
    const raw = String(node.status || '').toLowerCase();
    if (attn !== _highlight.status && raw !== _highlight.status) return false;
  }
  return true;
}

function _globeRotation(t) {
  const auto = !_prefersReducedMotion && _autoSpin && !_drag.active;
  return {
    rotY: _userRotY + (auto ? t * 0.00012 : 0),
    rotX: _userRotX + (auto ? Math.sin(t * 0.00012) * 0.15 : 0),
  };
}

function _initSphereNodes() {
  _sphereNodes = [];
  const latSteps = _isNarrow ? 12 : LAT_STEPS;
  const lonSteps = _isNarrow ? 22 : LON_STEPS;
  const extra = _isNarrow ? 38 : EXTRA_NODES;
  for (let i = 1; i < latSteps; i++) {
    const v = i / latSteps;
    const phi = v * Math.PI;
    const ringCount = Math.max(10, Math.round(lonSteps * Math.sin(phi)));
    for (let j = 0; j < ringCount; j++) {
      _sphereNodes.push({
        phi,
        theta: (j / ringCount) * Math.PI * 2,
        phase: Math.random() * Math.PI * 2,
        pulse: Math.random() * 1.4 + 0.4,
        size: Math.random() * 1.7 + 0.8,
      });
    }
  }
  for (let i = 0; i < extra; i++) {
    _sphereNodes.push({
      phi: Math.acos(1 - 2 * Math.random()),
      theta: Math.random() * Math.PI * 2,
      phase: Math.random() * Math.PI * 2,
      pulse: Math.random() * 1.8 + 0.7,
      size: Math.random() * 2.3 + 0.8,
    });
  }
}

function _initStars() {
  const count = _isNarrow ? 48 : STAR_COUNT;
  _stars = Array.from({ length: count }, () => ({
    x: Math.random() * _w,
    y: Math.random() * _h,
    s: Math.random() * 1.5 + 0.3,
    a: Math.random() * 0.8 + 0.15,
  }));
}

function _buildBranches(branchHealth) {
  _branchHealth = Array.isArray(branchHealth) ? branchHealth : [];
  const byId = Object.fromEntries(_branchHealth.map((b) => [b.id, b]));
  _branches = {};
  for (const [id, cfg] of Object.entries(BRANCH_SPHERE)) {
    const meta = byId[id];
    if (!meta && id === 'mycelia') continue;
    const m = meta || { state: 'idle', count: 0 };
    _branches[id] = {
      id,
      phi: cfg.phi,
      theta: cfg.theta,
      size: cfg.size * (1 + Math.min(0.25, (m.count || 0) * 0.03)),
      state: m.state || 'idle',
      action: m.action,
      summary: m.summary,
      phase: id.charCodeAt(0) * 0.07,
    };
  }
  for (const b of _branchHealth) {
    if (_branches[b.id] || !BRANCH_SPHERE[b.id]) continue;
    const cfg = BRANCH_SPHERE[b.id];
    _branches[b.id] = {
      id: b.id,
      phi: cfg.phi,
      theta: cfg.theta,
      size: cfg.size,
      state: b.state || 'idle',
      action: b.action,
      summary: b.summary,
      phase: b.id.charCodeAt(0) * 0.07,
    };
  }
}

function _buildGlobeGraph(globeGraph) {
  const g = globeGraph || {};
  _dataNodes = (g.nodes || []).map((n) => {
    const attn = _attentionStatus(n);
    const baseSize = n.size || 2.5;
    const sizeMul = attn ? ATTENTION[attn].sizeMul : 1;
    return {
      ...n,
      // Persist derived attention so highlight/status filters stay stable.
      attention: attn,
      phase: (_stableHash(n.id) % 1000) * 0.001,
      pulse: n.kind === 'agent' ? 1.4 : n.kind === 'project' ? 1.1 : attn === 'overdue' ? 1.35 : attn === 'due' ? 1.2 : 1.0,
      size: baseSize * sizeMul,
    };
  });
  _dataEdges = Array.isArray(g.edges) ? g.edges : [];
  _nodeById = Object.fromEntries(_dataNodes.map((n) => [n.id, n]));
}

function _buildParticles(inProgress) {
  _particles = [];
  if (inProgress <= 0 || !_branches.relay || !_branches.agency) return;
  const count = Math.min(10, inProgress * 2);
  for (let i = 0; i < count; i++) {
    _particles.push({
      t: i / count,
      speed: 0.12 + (i % 3) * 0.035,
      phase: Math.random() * Math.PI * 2,
    });
  }
}

function _projectNode(node, t) {
  const { rotY, rotX } = _globeRotation(t);
  const theta = node.theta + rotY + Math.sin(t * 0.0005 + (node.phase || 0)) * 0.01;
  const phi = node.phi + Math.sin(t * 0.0004 + (node.phase || 0)) * 0.008;

  let x = Math.sin(phi) * Math.cos(theta);
  let y = Math.cos(phi);
  let z = Math.sin(phi) * Math.sin(theta);

  const y2 = y * Math.cos(rotX) - z * Math.sin(rotX);
  const z2 = y * Math.sin(rotX) + z * Math.cos(rotX);
  y = y2;
  z = z2;

  const perspective = 520 / (520 + z * _globeRadius * 0.9);
  const R = _globeRadius * _viewScale;
  const px = _cx + x * R * perspective;
  const py = _cy + y * R * perspective;
  const twinkle = 0.72 + Math.sin(t * 0.0012 * (node.pulse || 1) + (node.phase || 0)) * 0.28;

  return { x: px, y: py, z, depth: perspective, alpha: twinkle, size: (node.size || 1) * perspective };
}

function _projectBranch(branch, t) {
  // The Odysseus core node is the hub at the literal center of the globe;
  // every other branch orbits the sphere surface and spokes radiate from here.
  if (branch.id === 'core') {
    return { x: _cx, y: _cy, z: 1, depth: 1, alpha: 1, size: branch.size };
  }
  return _projectNode(
    { phi: branch.phi, theta: branch.theta, phase: branch.phase, pulse: 1.2, size: branch.size },
    t,
  );
}

function _projectDataNode(node, t) {
  return _projectNode(
    {
      phi: node.phi,
      theta: node.theta,
      phase: node.phase,
      pulse: node.pulse,
      size: node.size || 2.5,
    },
    t,
  );
}

function _drawArc(a, b, intensity, rgb = '110,255,136') {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const nx = mx - _cx;
  const ny = my - _cy;
  const bulge = 1 + 0.12 * intensity;
  const cpx = _cx + nx * bulge;
  const cpy = _cy + ny * bulge;
  _ctx.strokeStyle = `rgba(${rgb},${0.06 + intensity * 0.08})`;
  _ctx.lineWidth = 0.8;
  _ctx.beginPath();
  _ctx.moveTo(a.x, a.y);
  _ctx.quadraticCurveTo(cpx, cpy, b.x, b.y);
  _ctx.stroke();
}

function _edgeIntensity(kind) {
  if (kind === 'attention' || kind === 'due') return 0.28;
  if (kind === 'activity' || kind === 'run') return 0.22;
  if (kind === 'tunnel' || kind === 'memory') return 0.14;
  return 0.1;
}

function _drawDataEdges(t) {
  if (!_dataEdges.length) return;
  const projected = new Map(
    _dataNodes.map((n) => [n.id, _projectDataNode(n, t)]),
  );
  for (const edge of _dataEdges) {
    const a = projected.get(edge.source);
    const b = projected.get(edge.target);
    if (!a || !b || a.z < -0.12 || b.z < -0.12) continue;
    const intensity = _edgeIntensity(edge.kind);
    let rgb = '110,255,136';
    if (edge.kind === 'attention' || edge.kind === 'due') rgb = '255,92,73';
    else if (edge.kind === 'activity' || edge.kind === 'run') rgb = '255,210,80';
    else if (edge.kind === 'tunnel' || edge.kind === 'memory') rgb = '80,200,240';
    else if (edge.kind === 'scheduled') rgb = '255,179,71';
    _drawArc(a, b, intensity, rgb);
  }
}

function _drawDataNodes(t) {
  const sorted = [..._dataNodes].sort((a, b) => {
    const pa = _projectDataNode(a, t);
    const pb = _projectDataNode(b, t);
    return pa.z - pb.z;
  });

  for (const node of sorted) {
    const p = _projectDataNode(node, t);
    if (p.z < -0.15) continue;
    const attn = _attentionStyle(node);
    const rgb = attn || _toneRgb(node.tone);
    const hi = _nodeMatchesHighlight(node);
    let pulse = 1;
    if (node.kind === 'agent' && node.status === 'running') {
      pulse = _prefersReducedMotion ? 1 : 1 + Math.sin(t * 0.005 + node.phase) * 0.18;
    } else if (node.kind === 'project') {
      pulse = _prefersReducedMotion ? 1 : 1 + Math.sin(t * 0.0018 + node.phase) * 0.08;
    } else if (attn && (node.attention === 'due' || node.attention === 'overdue')) {
      // Mild urgency pulse — skipped under prefers-reduced-motion.
      if (!_prefersReducedMotion) {
        const amp = node.attention === 'overdue' ? 0.16 : 0.1;
        pulse = 1 + Math.sin(t * 0.004 + node.phase) * amp;
      }
    }
    if (hi && !_prefersReducedMotion) {
      pulse *= 1 + Math.sin(t * 0.01 + node.phase) * 0.32;
    } else if (hi) {
      pulse *= 1.18; // static boost when motion is reduced
    }
    const r = Math.max(1.8, p.size * pulse * (hi ? 1.12 : 1));
    const alpha = p.z > 0 ? rgb.alpha : rgb.alpha * 0.55;
    let blur = attn
      ? attn.glowBlur
      : node.kind === 'project'
        ? 20
        : node.tone === 'urgent'
          ? 16
          : 12;
    if (hi) blur += 10;
    _ctx.shadowBlur = blur;
    _ctx.shadowColor = `rgba(${rgb.glow},${hi ? 1 : 0.9})`;
    _ctx.fillStyle = `rgba(${rgb.fill},${alpha})`;
    _ctx.beginPath();
    _ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    _ctx.fill();
    if (node.kind === 'project' || hi || node.attention === 'overdue') {
      _ctx.strokeStyle = `rgba(${rgb.glow},${hi ? 0.7 : 0.45})`;
      _ctx.lineWidth = hi ? 1.4 : 1;
      _ctx.beginPath();
      _ctx.arc(p.x, p.y, r + (hi ? 3.5 : 2.5), 0, Math.PI * 2);
      _ctx.stroke();
    }
  }
  _ctx.shadowBlur = 0;
}

function _drawCardConnectors(t) {
  if (!_cardAnchors.length) return;
  for (const anchor of _cardAnchors) {
    const branch = _branches[anchor.branch];
    if (!branch) continue;
    const bp = _projectBranch(branch, t);
    // Card must ALWAYS read as connected to its node: when the node rotates
    // to the back hemisphere we dim the line instead of dropping it.
    const behind = bp.z < -0.1;
    const lineAlpha = behind ? 0.22 : 0.6;

    const a = { x: anchor.x, y: anchor.y };
    const b = { x: bp.x, y: bp.y };

    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const nx = mx - _cx;
    const ny = my - _cy;
    const bulge = 1.06;
    const cpx = _cx + nx * bulge;
    const cpy = _cy + ny * bulge;

    // Bold, readable network line from the card edge to its data point.
    _ctx.shadowBlur = behind ? 0 : 7;
    _ctx.shadowColor = 'rgba(166,226,46,0.55)';
    _ctx.strokeStyle = `rgba(186,240,80,${lineAlpha})`;
    _ctx.lineWidth = 1.5;
    _ctx.beginPath();
    _ctx.moveTo(a.x, a.y);
    _ctx.quadraticCurveTo(cpx, cpy, b.x, b.y);
    _ctx.stroke();
    _ctx.shadowBlur = 0;

    // Endpoint plug at the card edge.
    _ctx.fillStyle = `rgba(210,255,190,${behind ? 0.4 : 0.95})`;
    _ctx.beginPath();
    _ctx.arc(a.x, a.y, 2.4, 0, Math.PI * 2);
    _ctx.fill();

    // Target ring around the data point so the eye lands on the right node.
    const ringR = Math.max(6, (bp.size || 4) + 4);
    _ctx.strokeStyle = `rgba(210,255,190,${behind ? 0.25 : 0.8})`;
    _ctx.lineWidth = 1.2;
    _ctx.beginPath();
    _ctx.arc(b.x, b.y, ringR, 0, Math.PI * 2);
    _ctx.stroke();

    // Travelling pulse: data flowing card ↔ node.
    const phase = (t * 0.00022 + (anchor.phase || 0)) % 1;
    const mt = 1 - phase;
    const qx = mt * mt * a.x + 2 * mt * phase * cpx + phase * phase * b.x;
    const qy = mt * mt * a.y + 2 * mt * phase * cpy + phase * phase * b.y;

    _ctx.shadowBlur = 8;
    _ctx.shadowColor = 'rgba(166,226,46,0.85)';
    _ctx.fillStyle = `rgba(210,255,190,${behind ? 0.45 : 0.95})`;
    _ctx.beginPath();
    _ctx.arc(qx, qy, 1.8, 0, Math.PI * 2);
    _ctx.fill();
    _ctx.shadowBlur = 0;
  }
}

function _drawRootTendrils(t) {
  const core = _branches.core;
  if (!core) return;
  const base = _projectBranch(core, t);
  if (base.z < -0.05) return;

  const rootCount = 7;
  for (let i = 0; i < rootCount; i++) {
    const spread = (i - (rootCount - 1) / 2) * 0.22;
    _ctx.strokeStyle = `rgba(90,255,120,${0.04 + (i % 2) * 0.02})`;
    _ctx.lineWidth = 0.7;
    _ctx.beginPath();
    _ctx.moveTo(base.x, base.y + base.size * 0.5);
    let px = base.x;
    let py = base.y + base.size * 0.5;
    for (let s = 1; s <= 14; s++) {
      const frac = s / 14;
      const drop = frac * _globeRadius * 0.55;
      const sway = Math.sin(t * 0.0008 + i + frac * 2) * 8 * frac;
      px = base.x + spread * _globeRadius * 0.35 * frac + sway;
      py = base.y + base.size * 0.5 + drop;
      _ctx.lineTo(px, py);
    }
    _ctx.stroke();
  }
}

function _draw(t) {
  if (!_ctx || !_canvas) return;
  _frame = requestAnimationFrame(_draw);
  if (_paused) return;

  _ctx.clearRect(0, 0, _w, _h);

  const halo = _ctx.createRadialGradient(_cx, _cy, 10, _cx, _cy, _globeRadius * 1.65);
  halo.addColorStop(0, 'rgba(235,255,238,0.18)');
  halo.addColorStop(0.18, 'rgba(148,255,165,0.16)');
  halo.addColorStop(0.52, 'rgba(64,220,96,0.12)');
  halo.addColorStop(1, 'rgba(0,0,0,0)');
  _ctx.fillStyle = halo;
  _ctx.beginPath();
  _ctx.arc(_cx, _cy, _globeRadius * 1.65, 0, Math.PI * 2);
  _ctx.fill();

  for (const s of _stars) {
    _ctx.fillStyle = `rgba(140,255,165,${s.a})`;
    _ctx.beginPath();
    _ctx.arc(s.x, s.y, s.s, 0, Math.PI * 2);
    _ctx.fill();
  }

  const pts = _sphereNodes.map((node) => _projectNode(node, t)).sort((a, b) => a.z - b.z);

  _ctx.strokeStyle = 'rgba(110,255,136,0.08)';
  _ctx.lineWidth = 1;
  _ctx.beginPath();
  _ctx.arc(_cx, _cy, _globeRadius, 0, Math.PI * 2);
  _ctx.stroke();

  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    if (a.z < -0.15) continue;
    for (let j = i + 1; j < Math.min(i + 10, pts.length); j++) {
      const b = pts[j];
      if (b.z < -0.15) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const d = Math.hypot(dx, dy);
      if (d < 34) {
        const alpha = (1 - d / 34) * 0.14 * ((a.depth + b.depth) / 2);
        _ctx.strokeStyle = `rgba(110,255,136,${alpha})`;
        _ctx.lineWidth = 0.7;
        _ctx.beginPath();
        _ctx.moveTo(a.x, a.y);
        _ctx.lineTo(b.x, b.y);
        _ctx.stroke();
      }
    }
  }

  for (let i = 0; i < pts.length; i += 22) {
    const a = pts[i];
    const b = pts[(i * 7 + 31) % pts.length];
    if (a.z > -0.05 && b.z > -0.05) {
      _drawArc(a, b, (a.depth + b.depth) / 2);
    }
  }

  const { rotY, rotX } = _globeRotation(t);
  const meridians = 6;
  for (let m = 0; m < meridians; m++) {
    const meridianRotation = rotY + (m / meridians) * Math.PI / 3;
    _ctx.strokeStyle = 'rgba(110,255,136,0.05)';
    _ctx.lineWidth = 0.8;
    _ctx.beginPath();
    for (let s = 0; s <= 60; s++) {
      const phi = (s / 60) * Math.PI;
      let x = Math.sin(phi) * Math.cos(meridianRotation);
      let y = Math.cos(phi);
      let z = Math.sin(phi) * Math.sin(meridianRotation);
      const y2 = y * Math.cos(rotX) - z * Math.sin(rotX);
      const z2 = y * Math.sin(rotX) + z * Math.cos(rotX);
      y = y2;
      z = z2;
      const perspective = 520 / (520 + z * _globeRadius * 0.9);
      const px = _cx + x * _globeRadius * perspective;
      const py = _cy + y * _globeRadius * perspective;
      if (s === 0) _ctx.moveTo(px, py);
      else _ctx.lineTo(px, py);
    }
    _ctx.stroke();
  }

  for (const p of pts) {
    const glow = p.z > 0 ? 14 : 8;
    _ctx.shadowBlur = _isNarrow ? 0 : glow;
    _ctx.shadowColor = p.z > 0 ? 'rgba(198,255,205,0.95)' : 'rgba(120,255,145,0.7)';
    _ctx.fillStyle = p.z > 0
      ? `rgba(238,255,241,${0.68 + p.alpha * 0.24})`
      : `rgba(120,255,145,${0.3 + p.alpha * 0.34})`;
    _ctx.beginPath();
    _ctx.arc(p.x, p.y, Math.max(0.8, p.size), 0, Math.PI * 2);
    _ctx.fill();
  }
  _ctx.shadowBlur = 0;

  _drawDataEdges(t);
  _drawDataNodes(t);
  _drawCardConnectors(t);
  _drawRootTendrils(t);

  const corePos = _branches.core ? _projectBranch(_branches.core, t) : null;
  for (const branch of Object.values(_branches)) {
    if (branch.id === 'core') continue;
    const bp = _projectBranch(branch, t);
    if (bp.z < -0.12 || !corePos || corePos.z < -0.12) continue;
    const rgb = _stateRgb(branch.state);
    const intensity = branch.state === 'busy' ? 0.22 : branch.state === 'idle' ? 0.08 : 0.14;
    _ctx.strokeStyle = `rgba(${rgb.glow},${intensity})`;
    _ctx.lineWidth = branch.state === 'busy' ? 1.2 : 0.9;
    _ctx.beginPath();
    _ctx.moveTo(corePos.x, corePos.y);
    _ctx.lineTo(bp.x, bp.y);
    _ctx.stroke();
  }

  for (const branch of Object.values(_branches)) {
    const bp = _projectBranch(branch, t);
    if (bp.z < -0.15) continue;
    const rgb = _stateRgb(branch.state);
    const pulse = branch.state === 'busy'
      ? 1 + Math.sin(t * 0.004 + branch.phase) * 0.15
      : 1 + Math.sin(t * 0.0015 + branch.phase) * 0.06;
    const r = Math.max(2.2, bp.size * pulse);
    _ctx.shadowBlur = branch.id === 'core' ? 22 : branch.state === 'busy' ? 18 : 14;
    _ctx.shadowColor = `rgba(${rgb.glow},0.95)`;
    _ctx.fillStyle = `rgba(${rgb.fill},${bp.z > 0 ? 0.92 : 0.55})`;
    _ctx.beginPath();
    _ctx.arc(bp.x, bp.y, r, 0, Math.PI * 2);
    _ctx.fill();
    if (branch.id === 'core') {
      _ctx.strokeStyle = 'rgba(198,255,205,0.35)';
      _ctx.lineWidth = 1;
      _ctx.beginPath();
      _ctx.arc(bp.x, bp.y, r + 3, 0, Math.PI * 2);
      _ctx.stroke();
    }
  }
  _ctx.shadowBlur = 0;

  if (_particles.length && _branches.relay && _branches.agency) {
    const relay = _projectBranch(_branches.relay, t);
    const agency = _projectBranch(_branches.agency, t);
    if (relay.z > -0.1 && agency.z > -0.1) {
      const mx = (relay.x + agency.x) / 2;
      const my = (relay.y + agency.y) / 2 - _globeRadius * 0.08;
      for (const p of _particles) {
        const phase = (p.t + t * 0.00015 * p.speed) % 1;
        const mt = 1 - phase;
        const px = mt * mt * relay.x + 2 * mt * phase * mx + phase * phase * agency.x;
        const py = mt * mt * relay.y + 2 * mt * phase * my + phase * phase * agency.y;
        _ctx.shadowBlur = 10;
        _ctx.shadowColor = 'rgba(127,255,0,0.9)';
        _ctx.fillStyle = 'rgba(200,255,210,0.95)';
        _ctx.beginPath();
        _ctx.arc(px, py, 2.2, 0, Math.PI * 2);
        _ctx.fill();
      }
      _ctx.shadowBlur = 0;
    }
  }
}

function _resize() {
  if (!_mount || !_canvas || !_ctx) return;
  const wasNarrow = _isNarrow;
  _isNarrow = Math.max(1, _mount.clientWidth) < 600;
  const dpr = Math.min(window.devicePixelRatio || 1, _isNarrow ? 1.5 : 2);
  _w = Math.max(1, _mount.clientWidth);
  _h = Math.max(1, _mount.clientHeight);
  _canvas.width = _w * dpr;
  _canvas.height = _h * dpr;
  _canvas.style.width = `${_w}px`;
  _canvas.style.height = `${_h}px`;
  _ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  _cx = _w / 2;
  _cy = _h / 2 - Math.min(24, _h * 0.04);
  _globeRadius = Math.min(_w, _h) * 0.245;
  if (wasNarrow !== _isNarrow || !_sphereNodes.length) {
    _initSphereNodes();
    _initStars();
  }
}

function _pointerCoords(event) {
  const rect = _mount.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function _hitTestAt(x, y, t) {
  const dataHits = _dataNodes
    .map((node) => ({ node, p: _projectDataNode(node, t) }))
    .filter(({ p }) => p.z > -0.08)
    .sort((a, b) => b.p.z - a.p.z);

  for (const { node, p } of dataHits) {
    const hitR = Math.max(10, (node.size || 2.5) * p.depth * 2.4);
    if (Math.hypot(p.x - x, p.y - y) < hitR) return node;
  }

  let best = null;
  let bestDist = Infinity;
  for (const branch of Object.values(_branches)) {
    const p = _projectBranch(branch, t);
    if (p.z < -0.08) continue;
    const d = Math.hypot(p.x - x, p.y - y);
    const hitR = Math.max(14, branch.size * p.depth * 2.8);
    if (d < hitR && d < bestDist) {
      bestDist = d;
      best = branch;
    }
  }
  return best;
}

function _showTooltip(node, x, y) {
  if (!_tooltip || !node) return;
  const label = node.label || node.id || '';
  const summary = node.summary || '';
  const chip = _statusChipText(node);
  const parts = [];
  if (chip) parts.push(chip);
  if (label) parts.push(label);
  if (summary && summary !== label) parts.push(summary);
  _tooltip.textContent = parts.join(' — ') || label;
  _tooltip.style.left = `${Math.min(x + 12, _w - 220)}px`;
  _tooltip.style.top = `${Math.max(y - 28, 8)}px`;
  _tooltip.style.opacity = '1';
  const attn = _attentionStyle(node);
  if (attn) {
    _tooltip.style.borderColor = `rgba(${attn.glow},0.45)`;
    _tooltip.style.boxShadow = `0 4px 16px rgba(0,0,0,0.45), 0 0 8px rgba(${attn.glow},0.25)`;
  } else {
    _tooltip.style.borderColor = '';
    _tooltip.style.boxShadow = '';
  }
}

function _hideTooltip() {
  if (_tooltip) _tooltip.style.opacity = '0';
}

function _ensurePopup() {
  if (_popup || !_mount) return;
  const el = document.createElement('div');
  el.className = 'cmd-scene-popup';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-hidden', 'true');
  el.innerHTML =
    '<div class="cmd-scene-popup-h"></div>' +
    '<div class="cmd-scene-popup-chip" style="display:none;font-size:9px;letter-spacing:0.16em;text-transform:uppercase;padding:2px 6px;margin:0 0 6px;border:1px solid;width:fit-content;"></div>' +
    '<div class="cmd-scene-popup-line cmd-scene-popup-label"></div>' +
    '<div class="cmd-scene-popup-line cmd-scene-popup-summary"></div>' +
    '<div class="cmd-scene-popup-line cmd-scene-popup-meta"></div>' +
    '<div class="cmd-scene-popup-cta" role="button" tabindex="0">OPEN &#9656;</div>';
  _mount.appendChild(el);
  _popup = el;
  _popup.querySelector('.cmd-scene-popup-cta')?.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (_popupNode?.action) _onNodeClick?.(_popupNode.action, _popupNode.target_id || _popupNode.id);
    _hidePopup();
  });
}

function _showPopup(node, x, y, t) {
  if (!_popup) _ensurePopup();
  if (!_popup || !node) return;
  _popupNode = node;
  const p = _projectDataNode(node, t);
  const header = _popupHeader(node);
  const label = node.label || node.id || '';
  const summary = node.summary || '';
  const chipText = _statusChipText(node);
  const attn = _attentionStyle(node);
  const metaParts = [];
  if (node.branch) metaParts.push(node.branch);
  if (attn) metaParts.push(attn.label.toLowerCase());
  else if (node.tone) metaParts.push(node.tone);
  const meta = metaParts.join(' · ');
  _popup.querySelector('.cmd-scene-popup-h').textContent = header;
  _popup.querySelector('.cmd-scene-popup-label').textContent = label;
  _popup.querySelector('.cmd-scene-popup-summary').textContent = summary;
  _popup.querySelector('.cmd-scene-popup-meta').textContent = meta;
  const chip = _popup.querySelector('.cmd-scene-popup-chip');
  if (chip) {
    if (chipText && attn) {
      chip.textContent = chipText;
      chip.style.display = '';
      chip.style.color = attn.hex;
      chip.style.borderColor = `rgba(${attn.glow},0.55)`;
      chip.style.background = `rgba(${attn.glow},0.1)`;
      chip.style.textShadow = `0 0 6px rgba(${attn.glow},0.45)`;
    } else {
      chip.style.display = 'none';
      chip.textContent = '';
    }
  }
  const cta = _popup.querySelector('.cmd-scene-popup-cta');
  if (cta) {
    cta.style.display = node.action ? '' : 'none';
    cta.innerHTML = _ctaLabel(node);
    if (attn) {
      cta.style.color = attn.hex;
      cta.style.borderColor = `rgba(${attn.glow},0.55)`;
    } else {
      cta.style.color = '';
      cta.style.borderColor = '';
    }
  }
  // Anchor beside the node, clamped to the mount.
  _popup.style.opacity = '1';
  _popup.setAttribute('aria-hidden', 'false');
  const pw = _popup.offsetWidth || 220;
  const ph = _popup.offsetHeight || 96;
  let px = p.x + 14;
  let py = p.y - ph - 8;
  if (px + pw > _w - 8) px = p.x - pw - 14;
  if (px < 8) px = Math.max(8, Math.min(p.x + 14, _w - pw - 8));
  if (py < 8) py = p.y + 14;
  if (py + ph > _h - 8) py = Math.max(8, _h - ph - 8);
  _popup.style.left = `${px}px`;
  _popup.style.top = `${py}px`;
  _onPopupOpen?.(node);
}

function _hidePopup() {
  if (!_popup) return;
  _popup.style.opacity = '0';
  _popup.setAttribute('aria-hidden', 'true');
  _popupNode = null;
}

function _onWheel(event) {
  if (!_mount) return;
  event.preventDefault();
  const factor = Math.pow(ZOOM_STEP, -event.deltaY);
  _viewScale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, _viewScale * factor));
}

function _onDblClick(event) {
  if (!_mount) return;
  const { x, y } = _pointerCoords(event);
  const t = performance.now();
  const hit = _hitTestAt(x, y, t);
  if (!hit) {
    // Empty space: reset exploration — re-center zoom and resume auto-spin
    // (still respects reduced-motion and the mobile no-spin default).
    _viewScale = 1;
    _autoSpin = !_prefersReducedMotion && !_isNarrow;
    _hidePopup();
  }
}

function _onKeyDown(event) {
  if (event.key === 'Escape') _hidePopup();
}

function _onPointerDown(event) {
  if (!_mount) return;
  const p = _pointerCoords(event);
  _activePointers.set(event.pointerId, p);
  if (_activePointers.size === 2) {
    _pinch.active = true;
    _drag.active = false;
    _drag.moved = true;
    const pts = [..._activePointers.values()];
    _pinch.startDist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1;
    _pinch.startScale = _viewScale;
    _autoSpin = false;
    _hideTooltip();
    _hidePopup();
    return;
  }
  if (_activePointers.size === 1) {
    _drag.active = true;
    _drag.moved = false;
    _drag.startX = p.x;
    _drag.startY = p.y;
    _drag.lastX = p.x;
    _drag.lastY = p.y;
    _canvas?.setPointerCapture?.(event.pointerId);
    if (_canvas) _canvas.style.cursor = 'grabbing';
  }
}

function _onPointerMove(event) {
  if (!_mount) return;

  if (!_activePointers.has(event.pointerId)) {
    if (_drag.active || _pinch.active) return;
    const { x, y } = _pointerCoords(event);
    const t = performance.now();
    const hit = _hitTestAt(x, y, t);
    if (hit?.summary || hit?.label) _showTooltip(hit, x, y);
    else _hideTooltip();
    return;
  }

  const p = _pointerCoords(event);
  _activePointers.set(event.pointerId, p);

  if (_pinch.active && _activePointers.size >= 2) {
    const pts = [..._activePointers.values()];
    const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1;
    const factor = dist / _pinch.startDist;
    _viewScale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, _pinch.startScale * factor));
    return;
  }

  if (_drag.active) {
    const { x, y } = p;
    const dx = x - _drag.lastX;
    const dy = y - _drag.lastY;
    if (!_drag.moved && Math.hypot(x - _drag.startX, y - _drag.startY) > DRAG_THRESHOLD_PX) {
      _drag.moved = true;
      _autoSpin = false; // user is exploring — stop the spin so they can study the sphere
      _hideTooltip();
      _hidePopup();
    }
    if (_drag.moved) {
      _userRotY += dx * DRAG_SENSITIVITY;
      _userRotX += dy * DRAG_SENSITIVITY;
      _userRotX = Math.max(-1.2, Math.min(1.2, _userRotX));
    }
    _drag.lastX = x;
    _drag.lastY = y;
  }
}

function _onPointerUp(event) {
  if (!_mount) return;
  _activePointers.delete(event.pointerId);
  _canvas?.releasePointerCapture?.(event.pointerId);

  if (_pinch.active) {
    if (_activePointers.size < 2) _pinch.active = false;
    if (_activePointers.size === 1) {
      const [p] = [..._activePointers.values()];
      _drag.active = true;
      _drag.moved = true; // don't treat the lift as a tap
      _drag.startX = p.x; _drag.startY = p.y;
      _drag.lastX = p.x; _drag.lastY = p.y;
    } else {
      _drag.active = false;
      _drag.moved = false;
    }
    if (_canvas) _canvas.style.cursor = 'grab';
    return;
  }

  const { x, y } = _pointerCoords(event);
  if (_drag.active && !_drag.moved) {
    const t = performance.now();
    const hit = _hitTestAt(x, y, t);
    if (hit) {
      // Data nodes (project / agent / urgent / scheduled) open the terminal popup.
      // Branch hubs (core / mem / prod / ...) keep direct navigate behavior.
      if (hit.kind && POPUP_KINDS.has(hit.kind)) {
        _showPopup(hit, x, y, t);
      } else if (hit.action) {
        _onNodeClick?.(hit.action, hit.target_id || hit.id);
      }
    }
  }

  _drag.active = false;
  _drag.moved = false;
  if (_canvas) _canvas.style.cursor = 'grab';
}

function _onPointerLeave() {
  _drag.active = false;
  _drag.moved = false;
  _hideTooltip();
  if (_canvas) _canvas.style.cursor = 'grab';
}

function _ensureTooltip() {
  if (_tooltip || !_mount) return;
  _tooltip = document.createElement('div');
  _tooltip.className = 'cmd-scene-tooltip';
  _tooltip.setAttribute('aria-hidden', 'true');
  _mount.appendChild(_tooltip);
}

function _ensureLegend() {
  if (_legend || !_mount) return;
  const el = document.createElement('div');
  el.className = 'cmd-scene-legend';
  el.setAttribute('aria-label', 'Node status legend');
  Object.assign(el.style, {
    position: 'absolute',
    left: '10px',
    bottom: '10px',
    zIndex: '5',
    pointerEvents: 'none',
    font: "10px/1.45 'JetBrains Mono', 'Consolas', monospace",
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    color: '#9fb89f',
    background: 'rgba(6,14,8,0.78)',
    border: '1px solid rgba(127,255,0,0.28)',
    boxShadow: '0 0 12px rgba(0,0,0,0.4), 0 0 8px rgba(127,255,0,0.1)',
    padding: '7px 9px',
    userSelect: 'none',
  });
  const row = (key) => {
    const a = ATTENTION[key];
    return (
      `<div style="display:flex;align-items:center;gap:7px;margin-top:3px;">` +
      `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;` +
      `background:${a.hex};box-shadow:0 0 6px rgba(${a.glow},0.85);"></span>` +
      `<span style="color:${a.hex};text-shadow:0 0 5px rgba(${a.glow},0.35);">${a.label}</span>` +
      `</div>`
    );
  };
  el.innerHTML =
    `<div style="color:#7fff00;letter-spacing:0.18em;font-size:9px;margin-bottom:2px;` +
    `border-bottom:1px solid rgba(127,255,0,0.22);padding-bottom:4px;">STATUS</div>` +
    row('calm') +
    row('due') +
    row('overdue');
  _mount.appendChild(el);
  _legend = el;
}

function _destroyLegend() {
  if (_legend?.parentNode) _legend.parentNode.removeChild(_legend);
  _legend = null;
}

export function initCmdCenterScene(mountEl, { branchHealth, inProgress = 0, globeGraph, onNodeClick, onPopupOpen } = {}) {
  disposeCmdCenterScene();
  if (!mountEl) return false;

  _prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false;
  _isNarrow = Math.max(1, mountEl.clientWidth) < 600;
  _autoSpin = !_prefersReducedMotion && !_isNarrow;
  _userRotX = 0;
  _userRotY = 0;

  _mount = mountEl;
  _onNodeClick = onNodeClick || null;
  _onPopupOpen = onPopupOpen || null;
  _inProgress = inProgress;
  _paused = false;
  _viewScale = 1;
  _popupNode = null;

  _canvas = document.createElement('canvas');
  _canvas.setAttribute('data-engine', 'vault-network-canvas');
  _canvas.style.display = 'block';
  _canvas.style.cursor = 'grab';
  _ctx = _canvas.getContext('2d');
  mountEl.appendChild(_canvas);

  _buildBranches(branchHealth);
  _buildGlobeGraph(globeGraph);
  _buildParticles(inProgress);
  _ensureTooltip();
  _ensureLegend();

  _resizeObserver = new ResizeObserver(_resize);
  _resizeObserver.observe(mountEl);
  _resize();

  _canvas.addEventListener('pointerdown', _onPointerDown);
  _canvas.addEventListener('pointermove', _onPointerMove);
  _canvas.addEventListener('pointerup', _onPointerUp);
  _canvas.addEventListener('pointerleave', _onPointerLeave);
  _canvas.addEventListener('pointercancel', _onPointerUp);
  _canvas.addEventListener('wheel', _onWheel, { passive: false });
  _canvas.addEventListener('dblclick', _onDblClick);
  document.addEventListener('keydown', _onKeyDown);
  _dismissBinding = (ev) => {
    if (_popup && !_popup.contains(ev.target)) _hidePopup();
  };
  document.addEventListener('pointerdown', _dismissBinding, true);
  _frame = requestAnimationFrame(_draw);
  return true;
}

export function setCardAnchors(anchors) {
  _cardAnchors = (anchors || [])
    .filter((a) => a && a.branch)
    .map((a) => ({
      ...a,
      phase: (_stableHash(a.id || a.branch) % 1000) / 1000,
    }));
}

export function updateCmdCenterScene(branchHealth, inProgress = 0, globeGraph = null) {
  _inProgress = inProgress;
  if (!_ctx) return;
  _buildBranches(branchHealth);
  if (globeGraph) _buildGlobeGraph(globeGraph);
  _buildParticles(inProgress);
}

/**
 * Temporarily boost glow/pulse on matching data nodes (Brief Me sync).
 * Filters AND together when multiple are provided.
 * @param {{ branch?: string, status?: 'calm'|'due'|'overdue'|string, ids?: string[] }} opts
 * @param {number} [durationMs=3000] clamped to 2000–4000
 */
export function highlightNodes(opts = {}, durationMs = HIGHLIGHT_MS_DEFAULT) {
  const { branch, status, ids } = opts || {};
  const dur = Math.max(HIGHLIGHT_MS_MIN, Math.min(HIGHLIGHT_MS_MAX, Number(durationMs) || HIGHLIGHT_MS_DEFAULT));
  const idList = Array.isArray(ids) ? ids.map(String).filter(Boolean) : [];
  _highlight = {
    ids: idList.length ? new Set(idList) : null,
    branch: branch ? String(branch) : null,
    status: status ? String(status).toLowerCase() : null,
    until: performance.now() + dur,
  };
}

/** Clear any active highlight pulse immediately. */
export function clearHighlights() {
  _highlight = { ids: null, branch: null, status: null, until: 0 };
}

export function pauseCmdCenterScene() {
  _paused = true;
}

export function resumeCmdCenterScene() {
  _paused = false;
  if (!_frame && _ctx) _frame = requestAnimationFrame(_draw);
}

export function isCmdCenterSceneAutoSpin() {
  return _autoSpin;
}

export function toggleCmdCenterSceneAutoSpin() {
  _autoSpin = !_autoSpin;
  if (_autoSpin) _viewScale = 1; // resuming spin also re-centers zoom
  return _autoSpin;
}

export function disposeCmdCenterScene() {
  if (_frame) {
    cancelAnimationFrame(_frame);
    _frame = null;
  }
  if (_canvas) {
    _canvas.removeEventListener('pointerdown', _onPointerDown);
    _canvas.removeEventListener('pointermove', _onPointerMove);
    _canvas.removeEventListener('pointerup', _onPointerUp);
    _canvas.removeEventListener('pointerleave', _onPointerLeave);
    _canvas.removeEventListener('pointercancel', _onPointerUp);
    _canvas.removeEventListener('wheel', _onWheel);
    _canvas.removeEventListener('dblclick', _onDblClick);
  }
  document.removeEventListener('keydown', _onKeyDown);
  if (_dismissBinding) {
    document.removeEventListener('pointerdown', _dismissBinding, true);
    _dismissBinding = null;
  }
  if (_resizeObserver && _mount) {
    _resizeObserver.disconnect();
    _resizeObserver = null;
  }
  if (_tooltip?.parentNode) {
    _tooltip.parentNode.removeChild(_tooltip);
  }
  _destroyLegend();
  if (_canvas?.parentNode) {
    _canvas.parentNode.removeChild(_canvas);
  }
  _canvas = null;
  _ctx = null;
  _mount = null;
  _onNodeClick = null;
  _onPopupOpen = null;
  _tooltip = null;
  clearHighlights();
  if (_popup?.parentNode) _popup.parentNode.removeChild(_popup);
  _popup = null;
  _popupNode = null;
  _sphereNodes = [];
  _stars = [];
  _branches = {};
  _particles = [];
  _dataNodes = [];
  _dataEdges = [];
  _nodeById = {};
  _cardAnchors = [];
  _drag = { active: false, moved: false, startX: 0, startY: 0, lastX: 0, lastY: 0 };
  _activePointers.clear();
  _pinch = { active: false, startDist: 0, startScale: 1 };
}

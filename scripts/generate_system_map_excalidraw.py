"""Generate docs/odysseus-system-map.excalidraw — Agentic OS style map of the build.

Run:  python scripts/generate_system_map_excalidraw.py
Layout mirrors the "AGENTIC OS" reference: You -> Odysseus (conductor) ->
capability branches -> automation layer -> tools & integrations.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

random.seed(42)
_NOW = int(time.time() * 1000)
_ids = 0


def _id() -> str:
    global _ids
    _ids += 1
    return f"ody-map-{_ids:04d}"


def _base(kind: str, x: float, y: float, w: float, h: float, **kw) -> dict:
    el = {
        "id": _id(),
        "type": kind,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": kw.get("stroke", "#e4e4e7"),
        "backgroundColor": kw.get("bg", "transparent"),
        "fillStyle": "solid",
        "strokeWidth": kw.get("strokeWidth", 1),
        "strokeStyle": kw.get("strokeStyle", "solid"),
        "roughness": 1,
        "opacity": kw.get("opacity", 100),
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3} if kind == "rectangle" else None,
        "seed": random.randint(1, 2**31),
        "version": 1,
        "versionNonce": random.randint(1, 2**31),
        "isDeleted": False,
        "boundElements": None,
        "updated": _NOW,
        "link": None,
        "locked": False,
    }
    return el


def rect(x, y, w, h, stroke, bg="transparent", dashed=False, stroke_width=1):
    return _base(
        "rectangle", x, y, w, h,
        stroke=stroke, bg=bg,
        strokeStyle="dashed" if dashed else "solid",
        strokeWidth=stroke_width,
    )


def text(x, y, s, size=12, color="#e4e4e7", align="left", w=None):
    est_w = w if w is not None else max(20, len(s) * size * 0.62)
    el = _base("text", x, y, est_w, size * 1.25, stroke=color)
    el.update({
        "text": s,
        "fontSize": size,
        "fontFamily": 3,  # code font
        "textAlign": align,
        "verticalAlign": "top",
        "containerId": None,
        "originalText": s,
        "lineHeight": 1.25,
        "baseline": size,
    })
    return el


def ctext(cx, y, s, size=12, color="#e4e4e7"):
    """Center-aligned text around cx."""
    est_w = max(20, len(s) * size * 0.62)
    el = text(cx - est_w / 2, y, s, size=size, color=color, align="center", w=est_w)
    return el


def line(x1, y1, x2, y2, color="#52525b"):
    el = _base("line", x1, y1, x2 - x1, y2 - y1, stroke=color)
    el.update({
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": None,
    })
    return el


COL_W = 200
GAP = 16
X0 = 40
N_COLS = 9
TOTAL_W = N_COLS * COL_W + (N_COLS - 1) * GAP
CX = X0 + TOTAL_W / 2

BRANCHES = [
    {
        "name": "MEMORY", "sub": "foundations · always on",
        "stroke": "#22c55e", "bg": "#052e16",
        "items": [
            ("Memories DB", "/api/memory · timeline"),
            ("Memory search", "recall + embeddings"),
            ("AgentMemory relay", "/api/agentmemory"),
            ("Saved prompts", "prompt library"),
            ("MCP: mempalace", "external palace"),
        ],
    },
    {
        "name": "PRODUCTIVITY", "sub": "foundations · always on",
        "stroke": "#84cc16", "bg": "#1a2e05",
        "items": [
            ("Notes / Todos", "/api/notes · pins, due"),
            ("Scheduled tasks", "/api/tasks · cron/daily"),
            ("Calendar (CalDAV)", "/api/calendar · sync"),
            ("Morning brief", "daily digest task"),
            ("Home dashboard", "jump back in"),
        ],
    },
    {
        "name": "RESEARCH", "sub": "capabilities · modular",
        "stroke": "#38bdf8", "bg": "#082f49",
        "items": [
            ("Deep research", "/api/research · SSE"),
            ("Search providers", "services/search"),
            ("Perplexity agent", "pro search"),
            ("Video transcribe", "/api/transcribe/url"),
            ("Audio brief", "research -> audio"),
        ],
    },
    {
        "name": "CONTENT / DOCS", "sub": "capabilities · modular",
        "stroke": "#818cf8", "bg": "#1e1b4b",
        "items": [
            ("Document library", "/api/documents"),
            ("Doc versions", "history + canvas"),
            ("Visual report", "src/visual_report"),
            ("Gallery / images", "albums + stamps"),
            ("Image editor", "editor drafts"),
        ],
    },
    {
        "name": "EMAIL / COMMS", "sub": "capabilities · modular",
        "stroke": "#60a5fa", "bg": "#172554",
        "items": [
            ("Inbox (IMAP)", "/api/email · tags"),
            ("Email pollers", "background sync"),
            ("Scheduled sends", "outbox queue"),
            ("Fenced email tools", "agent-safe ops"),
            ("Gmail GOG bridge", "src/gmail_gog"),
        ],
    },
    {
        "name": "JOBS PIPELINE", "sub": "agency · revenue",
        "stroke": "#f59e0b", "bg": "#451a03",
        "items": [
            ("Email ingest", "job leads in"),
            ("Dedupe + parse", "normalize records"),
            ("Evaluator", "fit scoring 1-5"),
            ("Tailoring dispatch", "resume + cover"),
            ("Apply queue", "/api/jobs · followups"),
        ],
    },
    {
        "name": "VOICE", "sub": "capabilities · modular",
        "stroke": "#f472b6", "bg": "#500724",
        "items": [
            ("Realtime gateway", "WebRTC · barge-in"),
            ("Voice tools", "tool calls by voice"),
            ("STT service", "/api/stt"),
            ("TTS controls", "audio output"),
            ("SLO metrics", "/api/voice/stats"),
        ],
    },
    {
        "name": "AGENT RELAY", "sub": "cross-agent handoffs",
        "stroke": "#a78bfa", "bg": "#2e1065",
        "items": [
            ("Handoff packets", "cross-agent docs"),
            ("Agent bin", "needs attention"),
            ("Relay queue", "/api/handoff-relay"),
            ("Skills: Cursor/Claude", "integrations/"),
            ("Relay watcher", "scripts/*.ps1"),
        ],
    },
    {
        "name": "MODELS / OPS", "sub": "per build · swappable",
        "stroke": "#e879f9", "bg": "#4a044e", "dashed": True,
        "items": [
            ("Model endpoints", "/api/model-endpoints"),
            ("Cookbook serve", "local models · GPUs"),
            ("MCP manager", "/api/mcp"),
            ("Diagnostics", "/api/health · /ready"),
            ("API tokens", "ody_* agent access"),
        ],
    },
]

elements: list[dict] = []

# Title
elements.append(ctext(CX, 16, "O D Y S S E U S — A G E N T I C  O S", 22, "#f4f4f5"))
elements.append(ctext(CX, 52, "Odysseus as Your Personal AI Operating System", 11, "#a1a1aa"))

# You / Client
elements.append(rect(CX - 90, 84, 180, 40, "#facc15", "#292008"))
elements.append(ctext(CX, 96, "You / Tylar", 13, "#fde68a"))

# Conductor
elements.append(rect(CX - 130, 152, 260, 56, "#93c5fd", "#0c1a33", stroke_width=2))
elements.append(ctext(CX, 162, "ODYSSEUS (FastAPI)", 14, "#bfdbfe"))
elements.append(ctext(CX, 184, "the conductor — app.py", 9, "#7dd3fc"))
elements.append(line(CX, 124, CX, 152, "#facc15"))

# V.A.U.L.T. box (right of conductor)
elements.append(rect(CX + 200, 152, 280, 56, "#a6e22e", "#101a06"))
elements.append(ctext(CX + 340, 162, "V.A.U.L.T. CMD CENTER", 12, "#d9f99d"))
elements.append(ctext(CX + 340, 182, "live HUD over all branches — /cmd-center", 8, "#a3e635"))
elements.append(line(CX + 130, 180, CX + 200, 180, "#a6e22e"))

# System states (top right)
elements.append(rect(X0 + TOTAL_W - 380, 68, 380, 56, "#34d399", "#022c22", dashed=True))
elements.append(text(X0 + TOTAL_W - 366, 78, "SYSTEM STATES · LIVE", 9, "#6ee7b7"))
elements.append(text(X0 + TOTAL_W - 366, 96, "20+ route modules · 25+ tables · 9 branches · MCP + skills", 8, "#a7f3d0"))

# Branch columns
HDR_Y = 280
ITEM_H = 46
ITEM_GAP = 8
for i, br in enumerate(BRANCHES):
    x = X0 + i * (COL_W + GAP)
    ccx = x + COL_W / 2
    # connector from conductor
    elements.append(line(CX, 208, ccx, HDR_Y, "#3f3f46"))
    # header
    elements.append(rect(x, HDR_Y, COL_W, 48, br["stroke"], br["bg"], dashed=br.get("dashed", False), stroke_width=2))
    elements.append(ctext(ccx, HDR_Y + 8, br["name"], 12, br["stroke"]))
    elements.append(ctext(ccx, HDR_Y + 28, br["sub"], 7, "#a1a1aa"))
    # items
    y = HDR_Y + 48 + 10
    for name, caption in br["items"]:
        elements.append(rect(x, y, COL_W, ITEM_H, "#3f3f46", "#131513"))
        elements.append(text(x + 10, y + 7, name, 10, "#e4e4e7"))
        elements.append(text(x + 10, y + 26, caption, 7.5, "#8b8b94"))
        y += ITEM_H + ITEM_GAP

BOTTOM_Y = HDR_Y + 48 + 10 + 5 * (ITEM_H + ITEM_GAP) + 24

# Automation layer
elements.append(rect(X0, BOTTOM_Y, TOTAL_W, 56, "#ca8a04", "#2b2005"))
elements.append(ctext(CX, BOTTOM_Y + 8, "AUTOMATION LAYER — src/task_scheduler.py", 12, "#fde047"))
elements.append(ctext(
    CX, BOTTOM_Y + 30,
    "cron · daily/weekly · event triggers · webhooks · morning brief · housekeeping · cookbook serve lifecycle",
    8, "#facc15",
))

# Integrations row
INT_Y = BOTTOM_Y + 80
elements.append(rect(X0, INT_Y, TOTAL_W, 64, "#8b5cf6", "#17091f"))
elements.append(ctext(CX, INT_Y + 8, "TOOLS, INTEGRATIONS & AGENTS", 10, "#c4b5fd"))
elements.append(ctext(
    CX, INT_Y + 28,
    "Cursor · Claude Code · Codex · MCP (Docker / Notion / Firecrawl / mempalace) · IMAP/Gmail · CalDAV · Ollama/local · OpenAI · Anthropic · Perplexity",
    9, "#ddd6fe",
))

# Footer
elements.append(ctext(CX, INT_Y + 92, "foundations stay fixed — capabilities + custom branches swap per role — same days, infinite extensibility", 8, "#71717a"))

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "odysseus/scripts/generate_system_map_excalidraw.py",
    "elements": elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#0b0d0b"},
    "files": {},
}

out = Path(__file__).resolve().parents[1] / "docs" / "odysseus-system-map.excalidraw"
out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
print(f"Wrote {out} ({len(elements)} elements)")

"""Generate ssh_debugging.excalidraw from the Tailscale tunnel path decision diagram.

Run:  python scripts/generate_ssh_debugging_excalidraw.py
Each box, label, arrow, and card bullet is its own editable Excalidraw element.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

random.seed(77)
_NOW = int(time.time() * 1000)
_ids = 0

# Colors matching ssh_debugging.html
CYAN = "#22d3ee"
EMERALD = "#34d399"
VIOLET = "#a78bfa"
AMBER = "#fbbf24"
ROSE = "#fb7185"
SLATE = "#94a3b8"
WHITE = "#ffffff"
MUTED = "#64748b"
BG_CYAN = "#083344"
BG_EMERALD = "#064e3b"
BG_VIOLET = "#4c1d95"
BG_AMBER = "#78350f"
BG_ROSE = "#881337"
BG_SLATE = "#1e293b"
BG_DARK = "#0f172a"


def _id() -> str:
    global _ids
    _ids += 1
    return f"ssh-dbg-{_ids:04d}"


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
        "roughness": 0,
        "opacity": kw.get("opacity", 100),
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3} if kind in ("rectangle", "ellipse") else None,
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
        "rectangle",
        x,
        y,
        w,
        h,
        stroke=stroke,
        bg=bg,
        strokeStyle="dashed" if dashed else "solid",
        strokeWidth=stroke_width,
    )


def ellipse(x, y, w, h, stroke, bg="transparent", dashed=False, stroke_width=1):
    return _base(
        "ellipse",
        x,
        y,
        w,
        h,
        stroke=stroke,
        bg=bg,
        strokeStyle="dashed" if dashed else "solid",
        strokeWidth=stroke_width,
    )


def text(x, y, s, size=12, color="#e4e4e7", align="left", w=None):
    est_w = w if w is not None else max(20, len(s) * size * 0.58)
    el = _base("text", x, y, est_w, size * 1.25, stroke=color)
    el.update(
        {
            "text": s,
            "fontSize": size,
            "fontFamily": 3,
            "textAlign": align,
            "verticalAlign": "top",
            "containerId": None,
            "originalText": s,
            "lineHeight": 1.25,
            "baseline": size,
        }
    )
    return el


def ctext(cx, y, s, size=12, color="#e4e4e7"):
    est_w = max(20, len(s) * size * 0.58)
    return text(cx - est_w / 2, y, s, size=size, color=color, align="center", w=est_w)


def arrow(points, color=MUTED, stroke_width=2, dashed=False, end_arrow=True):
    """points: list of [x,y] absolute coords. Converted to relative."""
    x0, y0 = points[0]
    rel = [[p[0] - x0, p[1] - y0] for p in points]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    el = _base(
        "arrow",
        x0,
        y0,
        max(xs) - min(xs),
        max(ys) - min(ys),
        stroke=color,
        strokeWidth=stroke_width,
        strokeStyle="dashed" if dashed else "solid",
    )
    el["roundness"] = {"type": 2}
    el.update(
        {
            "points": rel,
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow" if end_arrow else None,
        }
    )
    return el


def line(x1, y1, x2, y2, color=MUTED, stroke_width=1.5, dashed=False, end_arrow=False):
    el = _base(
        "line" if not end_arrow else "arrow",
        x1,
        y1,
        x2 - x1,
        y2 - y1,
        stroke=color,
        strokeWidth=stroke_width,
        strokeStyle="dashed" if dashed else "solid",
    )
    el.update(
        {
            "points": [[0, 0], [x2 - x1, y2 - y1]],
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow" if end_arrow else None,
        }
    )
    if end_arrow:
        el["roundness"] = {"type": 2}
    return el


def card_block(x, y, w, title, title_color, bullets, border=None, bg=BG_DARK):
    """Info card: rectangle + title + each bullet as its own text element."""
    line_h = 16
    pad = 14
    header_h = 28
    h = pad + header_h + len(bullets) * line_h + pad
    els = [
        rect(x, y, w, h, border or title_color, bg=bg, stroke_width=1.5),
        text(x + pad, y + pad, title, size=13, color=title_color),
    ]
    for i, bullet in enumerate(bullets):
        els.append(
            text(
                x + pad,
                y + pad + header_h + i * line_h,
                f"• {bullet}",
                size=10,
                color=SLATE,
                w=w - pad * 2,
            )
        )
    return els, h


def build() -> list[dict]:
    els: list[dict] = []

    # ---- Header ----
    els.append(ellipse(40, 28, 14, 14, ROSE, bg=ROSE))
    els.append(text(64, 26, "Tailscale Tunnel Path — Three Options", size=22, color=WHITE))
    els.append(
        text(
            64,
            56,
            "Goal: VPS can reach the Mac mini's agentmemory daemon (port 3111) over the encrypted tailnet.",
            size=12,
            color=SLATE,
        )
    )
    els.append(
        text(
            40,
            90,
            "Three paths from VPS to Mac mini's :3111 (agentmemory daemon)",
            size=12,
            color=CYAN,
        )
    )

    # ---- Devices ----
    # LAPTOP
    els.append(rect(40, 130, 160, 80, CYAN, bg=BG_CYAN, stroke_width=1.5))
    els.append(ctext(120, 145, "LAPTOP", size=14, color=WHITE))
    els.append(ctext(120, 168, "100.93.33.88", size=11, color=SLATE))
    els.append(ctext(120, 188, "Tailscale: kernel mode", size=10, color=CYAN))

    # MAC MINI
    els.append(rect(900, 130, 160, 90, EMERALD, bg=BG_EMERALD, stroke_width=2))
    els.append(ctext(980, 145, "MAC MINI", size=14, color=WHITE))
    els.append(ctext(980, 168, "100.90.244.101", size=11, color=SLATE))
    els.append(ctext(980, 186, "iii daemon :3111", size=10, color=EMERALD))
    els.append(ctext(980, 202, "127.0.0.1 only (wrapper bug)", size=9, color=ROSE))

    # PATH C label (recommended)
    els.append(rect(470, 150, 180, 60, EMERALD, bg="#064e3b", stroke_width=1.5))
    els.append(ctext(560, 160, "PATH C — RECOMMENDED", size=12, color=EMERALD))
    els.append(ctext(560, 180, "Laptop as ProxyJump", size=11, color=WHITE))
    els.append(ctext(560, 196, "VPS → laptop → mini", size=9, color=SLATE))

    # Tailnet hub
    els.append(ellipse(360, 230, 400, 48, CYAN, bg=BG_CYAN, dashed=True, stroke_width=1))
    els.append(ctext(560, 240, "Tailscale tailnet", size=12, color=CYAN))
    els.append(
        ctext(560, 258, "tail42ce2d.ts.net · DERP relay · WireGuard", size=10, color=SLATE)
    )

    # PATH B label
    els.append(rect(220, 300, 170, 55, VIOLET, bg=BG_VIOLET, stroke_width=1))
    els.append(ctext(305, 310, "PATH B", size=12, color=VIOLET))
    els.append(ctext(305, 328, "Sidecar container", size=11, color=WHITE))
    els.append(ctext(305, 344, "shared socket volume", size=9, color=SLATE))

    # PATH A label
    els.append(rect(470, 300, 180, 55, AMBER, bg=BG_AMBER, stroke_width=1))
    els.append(ctext(560, 310, "PATH A", size=12, color=AMBER))
    els.append(ctext(560, 328, "/dev/net/tun + iptables", size=11, color=WHITE))
    els.append(ctext(560, 344, "Hostinger rebuild", size=9, color=SLATE))

    # VPS CONTAINER
    els.append(rect(380, 400, 360, 200, SLATE, bg=BG_DARK, stroke_width=2))
    els.append(ctext(560, 415, "VPS CONTAINER", size=15, color=WHITE))
    els.append(ctext(560, 438, "b5c08b733c93 / 100.90.120.97", size=11, color=SLATE))
    els.append(ctext(560, 456, "containerd, seccomp docker-default", size=10, color=SLATE))
    els.append(ctext(560, 472, "no /dev/net/tun, no iptables", size=10, color=SLATE))

    # tailscaled
    els.append(rect(410, 500, 130, 80, SLATE, bg=BG_SLATE, stroke_width=1.2))
    els.append(ctext(475, 512, "tailscaled", size=12, color=WHITE))
    els.append(ctext(475, 532, "--tun=userspace", size=10, color=SLATE))
    els.append(ctext(475, 548, "TCP-to-peer times out", size=9, color=ROSE))
    els.append(ctext(475, 564, "silent drop", size=9, color=SLATE))

    # SSH tunnel
    els.append(rect(570, 500, 140, 80, CYAN, bg=BG_CYAN, stroke_width=1.2))
    els.append(ctext(640, 512, "SSH tunnel", size=12, color=WHITE))
    els.append(ctext(640, 532, "-L 3111:127.0.0.1:3111", size=9, color=SLATE))
    els.append(ctext(640, 548, "localhost:3111 ready", size=9, color=CYAN))
    els.append(ctext(640, 564, "agentmemory client", size=9, color=SLATE))

    # HOSTINGER HOST
    els.append(
        rect(380, 640, 360, 70, AMBER, bg="#292008", dashed=True, stroke_width=1.5)
    )
    els.append(ctext(560, 652, "HOSTINGER HOST (Host OS)", size=12, color=AMBER))
    els.append(ctext(560, 672, "2.24.31.124 — srv1836102.hstgr.cloud", size=10, color=SLATE))
    els.append(
        ctext(560, 690, "containerd + Traefik — controls container rebuild", size=10, color=AMBER)
    )

    # ---- Path arrows (each editable) ----
    # Path A: VPS → Mac mini (amber)
    els.append(
        arrow(
            [[560, 400], [560, 360], [900, 200]],
            color=AMBER,
            stroke_width=2,
        )
    )
    # Path A dashed down to host
    els.append(
        line(560, 600, 560, 638, color=AMBER, stroke_width=1.5, dashed=True, end_arrow=True)
    )

    # Path B: sidecar → VPS (violet)
    els.append(
        arrow(
            [[240, 640], [240, 540], [410, 540]],
            color=VIOLET,
            stroke_width=2,
        )
    )

    # Path C: VPS → Laptop (emerald)
    els.append(
        arrow(
            [[410, 540], [120, 540], [120, 210]],
            color=EMERALD,
            stroke_width=2.5,
        )
    )
    # Path C: Laptop → Mac mini via top
    els.append(
        arrow(
            [[200, 160], [470, 160], [560, 160]],
            color=EMERALD,
            stroke_width=2.5,
            end_arrow=False,
        )
    )
    els.append(
        arrow(
            [[650, 160], [900, 160], [980, 220]],
            color=EMERALD,
            stroke_width=2.5,
        )
    )
    # Path C return / tunnel into SSH box
    els.append(
        arrow(
            [[980, 220], [980, 360], [710, 500]],
            color=EMERALD,
            stroke_width=2.5,
        )
    )

    # ---- Legend ----
    ly = 760
    els.append(text(40, ly, "Legend", size=12, color=WHITE))
    els.append(rect(40, ly + 24, 16, 12, CYAN, bg=BG_CYAN))
    els.append(text(64, ly + 22, "Machine on tailnet", size=10, color=SLATE))
    els.append(line(220, ly + 30, 250, ly + 30, color=EMERALD, stroke_width=2, end_arrow=True))
    els.append(text(258, ly + 22, "Recommended path", size=10, color=SLATE))
    els.append(line(420, ly + 30, 450, ly + 30, color=AMBER, stroke_width=2, end_arrow=True))
    els.append(text(458, ly + 22, "Cleanest path (blocked)", size=10, color=SLATE))
    els.append(line(640, ly + 30, 670, ly + 30, color=VIOLET, stroke_width=2, end_arrow=True))
    els.append(text(678, ly + 22, "Alternative", size=10, color=SLATE))
    els.append(rect(40, ly + 48, 16, 12, ROSE, bg=BG_ROSE))
    els.append(text(64, ly + 46, "Known blocker / constraint", size=10, color=SLATE))

    # ---- Info cards (row 1: three paths) ----
    card_y = 860
    card_w = 340
    gap = 20

    cards_r1 = [
        (
            AMBER,
            "Path A — Cleanest (blocked)",
            [
                "Rebuild Hostinger with --device=/dev/net/tun --cap-add=NET_ADMIN + iptables",
                "Switch tailscaled from userspace to kernel mode",
                "Direct TCP from VPS → mini over tailnet works",
                "Tunnel script already staged — flips one flag and runs",
                "BLOCKED: Hostinger containerd blocks device passthrough",
                "Time to green: depends on Hostinger (days)",
            ],
        ),
        (
            VIOLET,
            "Path B — Sidecar (medium)",
            [
                "Second container with /dev/net/tun, Tailscale kernel-mode",
                "Share the tailnet socket via a volume mount",
                "VPS gets kernel-mode benefits without rebuilding main",
                "BLOCKED: Hostinger multi-container depends on plan",
                "Time to green: hours if allowed, never if not",
            ],
        ),
        (
            EMERALD,
            "Path C — Laptop ProxyJump (today)",
            [
                "VPS SSH with -J tylar@100.93.33.88 as the jump",
                "Laptop relays to mini over tailnet (kernel-mode OK)",
                "Tunnel terminates at VPS localhost:3111 same as Path A",
                "Trade-off: brittle — needs laptop online",
                "Time to green: 30 min from your go",
            ],
        ),
    ]

    x = 40
    max_h = 0
    for color, title, bullets in cards_r1:
        block, h = card_block(x, card_y, card_w, title, color, bullets, border=color)
        els.extend(block)
        max_h = max(max_h, h)
        x += card_w + gap

    # ---- Info cards (row 2) ----
    card_y2 = card_y + max_h + 24
    cards_r2 = [
        (
            CYAN,
            "Why Path A is blocked (root cause)",
            [
                "Hostinger containerd: docker-default seccomp deny-by-default",
                "mknod /dev/net/tun succeeds (root has CAP_MKNOD)",
                "open(/dev/net/tun) → EPERM — cgroup whitelist excludes char-major-10-200",
                "iptables not in image — needed for kernel-mode Tailscale NAT",
                "CAP_NET_ADMIN cannot bypass cgroup device policy",
                "Needs Hostinger orchestrator device passthrough (policy change)",
            ],
        ),
        (
            ROSE,
            "What works today (no tunnel needed)",
            [
                "tailscale ping to any peer — control plane via DERP",
                "Outbound HTTPS to login.tailscale.com, github.com, controlplane",
                "All Hermes app functions (Claude Code, sessions, skills, cron)",
                "TinyFish Search + Fetch (free tier)",
                "Playwright local browser harness",
                "fzf, general shell tooling",
            ],
        ),
        (
            VIOLET,
            "What stays blocked until tunnel",
            [
                "AGENTMEMORY_URL=http://localhost:3111 from VPS — unreachable",
                "@agentmemory/agentmemory on VPS — install waiting on tunnel",
                "Cross-machine memory continuity (core goal)",
                "Direct TCP services to mini (only via laptop SSH relay)",
            ],
        ),
    ]

    x = 40
    for color, title, bullets in cards_r2:
        block, _ = card_block(x, card_y2, card_w, title, color, bullets, border=color)
        els.extend(block)
        x += card_w + gap

    # Footer
    els.append(
        ctext(
            560,
            card_y2 + 220,
            "Ras's Hermes Agent setup · Tailscale path decision · 2026-07-18",
            size=11,
            color=MUTED,
        )
    )

    return els


def main() -> None:
    elements = build()
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "odysseus/scripts/generate_ssh_debugging_excalidraw.py",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#020617",
        },
        "files": {},
    }
    out = Path(__file__).resolve().parents[1] / "ssh_debugging.excalidraw"
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(elements)} elements)")


if __name__ == "__main__":
    main()

r"""navi-du: shared scanning core.

Pure filesystem/data logic shared by the HTML renderer (navi_du.py) and the
terminal renderer (navi_du_tui.py). Nothing in here touches HTML, ANSI, or
Textual.
"""
from __future__ import annotations

import glob
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_TOP_CHILDREN = 40
MAX_DRILL_CHILDREN = 8  # how many of the biggest children get a level-2 expansion

# Family palette: shared color/label vocabulary for both renderers.
# `weight` only matters to the HTML dither renderer (occupancy density);
# the TUI just uses `cream` as a flat terminal background color.
FAMILIES = {
    "appdata":  {"cream": "#bff3ff", "weight": 0.62, "label": "AppData"},
    "programs": {"cream": "#e2c9ff", "weight": 0.70, "label": "Programs"},
    "user":     {"cream": "#d8ffb0", "weight": 0.55, "label": "User files"},
    "dev":      {"cream": "#ffe0a0", "weight": 0.68, "label": "Dev / code"},
    "wsl":      {"cream": "#ffc9f0", "weight": 0.50, "label": "WSL"},
    "system":   {"cream": "#d8d8d8", "weight": 0.35, "label": "System (Plus Part)"},
    "other":    {"cream": "#f4f4f4", "weight": 0.50, "label": "Other"},
}


def human(n: int) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return f"{n:.1f}TB"


def dir_size(path: str) -> tuple[int, int]:
    """Recursive byte total for a directory. Returns (bytes, error_count)."""
    total = 0
    errors = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return total, errors


def scan_children(path: str, expand_top_n: int = 0) -> tuple[list[dict], int]:
    """Immediate children of `path`, each with a recursive byte total.
    The `expand_top_n` biggest directory children also get their own
    one-level-deep children so a client can drill down without a server.
    """
    children: list[dict] = []
    loose_bytes = 0
    errors = 0
    try:
        with os.scandir(path) as it:
            dir_entries = []
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        dir_entries.append(entry)
                    else:
                        loose_bytes += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    errors += 1
    except OSError:
        return [], 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(dir_size, e.path): e for e in dir_entries}
        for fut in as_completed(futures):
            entry = futures[fut]
            sz, errs = fut.result()
            errors += errs
            if sz > 0:
                children.append({"name": entry.name, "path": entry.path, "bytes": sz, "children": []})

    if loose_bytes > 0:
        children.append({"name": "(loose files)", "path": path, "bytes": loose_bytes, "children": []})

    children.sort(key=lambda c: c["bytes"], reverse=True)

    if expand_top_n:
        for c in children[:expand_top_n]:
            if c["name"] == "(loose files)":
                continue
            grand, _ = scan_children(c["path"], expand_top_n=0)
            if len(grand) > MAX_TOP_CHILDREN:
                rest = grand[MAX_TOP_CHILDREN:]
                grand = grand[:MAX_TOP_CHILDREN]
                grand.append({"name": f"(+{len(rest)} more)", "path": c["path"],
                               "bytes": sum(g["bytes"] for g in rest), "children": []})
            c["children"] = grand

    if len(children) > MAX_TOP_CHILDREN:
        rest = children[MAX_TOP_CHILDREN:]
        children = children[:MAX_TOP_CHILDREN]
        children.append({"name": f"(+{len(rest)} more)", "path": path,
                           "bytes": sum(c["bytes"] for c in rest), "children": []})

    return children, errors


def find_wsl_vhdx() -> list[dict]:
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return []
    hits = []
    for pattern in (
        os.path.join(local, "Packages", "*ubuntu*", "LocalState", "ext4.vhdx"),
        os.path.join(local, "Packages", "*WSL*", "LocalState", "ext4.vhdx"),
        os.path.join(local, "Docker", "wsl", "data", "ext4.vhdx"),
    ):
        for p in glob.glob(pattern):
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            hits.append({"name": os.path.basename(os.path.dirname(os.path.dirname(p))), "path": p,
                          "bytes": sz, "children": []})
    return hits


def default_roots(quick: bool) -> list[dict]:
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    roaming = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    sysdrive = os.environ.get("SystemDrive", "C:") + "\\"

    roots = [
        {"name": "AppData\\Local", "path": local, "family": "appdata"},
        {"name": "code", "path": os.path.join(home, "code"), "family": "dev"},
    ]
    if quick:
        return [r for r in roots if os.path.isdir(r["path"])]

    roots += [
        {"name": "AppData\\Roaming", "path": roaming, "family": "appdata"},
        {"name": "Program Files", "path": os.path.join(sysdrive, "Program Files"), "family": "programs"},
        {"name": "Program Files (x86)", "path": os.path.join(sysdrive, "Program Files (x86)"), "family": "programs"},
        {"name": "Documents", "path": os.path.join(home, "Documents"), "family": "user"},
        {"name": "Downloads", "path": os.path.join(home, "Downloads"), "family": "user"},
        {"name": "Desktop", "path": os.path.join(home, "Desktop"), "family": "user"},
        {"name": "Videos", "path": os.path.join(home, "Videos"), "family": "user"},
    ]
    return [r for r in roots if os.path.isdir(r["path"])]


def drive_usage() -> tuple[str, int, int]:
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    usage = shutil.disk_usage(drive)
    return drive, usage.used, usage.total


def scan_root(meta: dict) -> dict:
    """Scan one root synchronously; safe to call from a worker thread."""
    children, errs = scan_children(meta["path"], expand_top_n=MAX_DRILL_CHILDREN)
    total_bytes = sum(c["bytes"] for c in children)
    return {**meta, "bytes": total_bytes, "errors": errs, "children": children}


def scan(quick: bool, on_root_done=None) -> dict:
    """Full synchronous scan. If `on_root_done(result_dict)` is given, it's
    called on the main thread as each root finishes (used for CLI progress
    printing). For a streaming/live UI, use scan_root() per-root instead."""
    t0 = time.time()
    roots_meta = default_roots(quick)
    total_errors = 0
    out_roots = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(scan_root, m) for m in roots_meta]
        for fut in as_completed(futures):
            r = fut.result()
            total_errors += r["errors"]
            out_roots.append(r)
            if on_root_done:
                on_root_done(r)

    if not quick:
        for w in find_wsl_vhdx():
            out_roots.append({"name": f"WSL: {w['name']}", "path": w["path"], "family": "wsl",
                               "bytes": w["bytes"], "errors": 0, "children": []})
            if on_root_done:
                on_root_done(out_roots[-1])

    out_roots.sort(key=lambda r: r["bytes"], reverse=True)
    drive, used, total = drive_usage()

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": os.environ.get("COMPUTERNAME", "this-machine"),
        "drive": drive,
        "drive_used": used,
        "drive_total": total,
        "scan_seconds": round(time.time() - t0, 1),
        "had_errors": total_errors > 0,
        "error_count": total_errors,
        "roots": out_roots,
    }

#!/usr/bin/env python
r"""navi-du-tui: NaviCust/PET-styled disk storage visualizer, in the terminal.

Same real scan as navi_du.py (folders -> byte-weighted hierarchy), but
rendered as chunky flat-colored "Program Part" blocks squarified into a
small Memory Map grid -- no browser, no dither, just a real Textual TUI you
run in Windows Terminal. Opens immediately and fills in as each root
finishes scanning.

Usage:
    python tools/navi_du_tui.py            # full scan
    python tools/navi_du_tui.py --quick    # AppData\Local + code\ only (fast)

Keys: Up/Down browse, Enter/click drills into a folder, Esc/Backspace goes
back up, r rescans, q quits.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.style import Style
from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, OptionList, ProgressBar, Static
from textual.widgets.option_list import Option

from navi_du_layout import layout_items
from navi_du_scan import FAMILIES, default_roots, drive_usage, find_wsl_vhdx, human, scan_root

MAX_TUI_BLOCKS = 14
MIN_BLOCK_SHARE = 0.015  # below this fraction of the current view, fold into "(+N more)"
GUTTER_COLOR = "#0a0c28"
LABEL_TEXT_COLOR = "#12122a"

# ---------------------------------------------------------------------------
# MegaMan-style NetNavi pixel sprite (stylized, compact, 2-frame blink).
# Half-rows: index 0 = center column, outward to the edge; mirrored at draw
# time. Same art as navi_du_template.html's header sprite, cropped to the
# helmet/visor (rows 0-9) to fit a terminal header strip.
_PAL = {"B": "#1c3fae", "b": "#3a63e0", "C": "#37f0ff", "K": "#0a1020", "R": "#ff3b4e"}
_HALF_OPEN = [
    ".B.......",
    ".BB......",
    "BBBB.....",
    "RbbBB....",
    "BbCbBB...",
    "BbCCbBB..",
    "BKKKbBBB.",
    "BKKKbBBB.",
    "BbCCbBBB.",
    "BbbbbBB..",
]
_HALF_BLINK = [row.replace("K", "b").replace("C", "b") if i in (6, 7) else row
               for i, row in enumerate(_HALF_OPEN)]


def family_color(family: str) -> str:
    return FAMILIES.get(family, FAMILIES["other"])["cream"]


class NaviSprite(Static):
    blink: reactive[bool] = reactive(False)

    def render(self):
        half = _HALF_BLINK if self.blink else _HALF_OPEN
        text = Text()
        for row in half:
            mirrored = row[1:][::-1] + row
            for ch in mirrored:
                color = _PAL.get(ch)
                text.append("\u2588", style=color if color else "")
            text.append("\n")
        return text


class Layer:
    __slots__ = ("label", "items", "family")

    def __init__(self, label: str, items: list[dict], family: str | None = None):
        self.label = label
        self.items = items
        self.family = family


class MemoryMap(Widget):
    """Squarified, flat-colored 'Memory Map' -- the chunky NaviCust grid."""

    can_focus = False

    class BlockClicked(Message):
        def __init__(self, idx: int) -> None:
            self.idx = idx
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items: list[dict] = []
        self._cursor = 0
        self._dirty = True
        self._grid: list[list[int]] | None = None
        self._bounds: dict[int, tuple[int, int, int, int]] = {}
        self._labels: dict[int, list[tuple[int, int, str]]] = {}

    def set_items(self, items: list[dict], cursor: int) -> None:
        self._items = items
        self._cursor = cursor
        self._dirty = True
        self.refresh()

    def set_cursor(self, cursor: int) -> None:
        self._cursor = cursor
        self.refresh()

    def on_resize(self, event) -> None:
        self._dirty = True

    def _ensure_layout(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        w, h = self.size.width, self.size.height
        self._grid = None
        self._bounds = {}
        self._labels = {}
        if w <= 0 or h <= 0 or not self._items:
            return

        tagged = []
        for i, it in enumerate(self._items):
            t = dict(it)
            t["_i"] = i
            tagged.append(t)
        placed = layout_items(tagged, w, h)

        grid = [[-1] * w for _ in range(h)]
        bounds: dict[int, tuple[int, int, int, int]] = {}
        for p in placed:
            idx = p.item["_i"]
            x0, y0 = int(round(p.x)), int(round(p.y))
            x1, y1 = int(round(p.x + p.w)), int(round(p.y + p.h))
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1), min(h, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            bounds[idx] = (x0, y0, x1, y1)
            inset = 1 if (x1 - x0 >= 3 and y1 - y0 >= 3) else 0
            for yy in range(y0 + inset, y1 - inset):
                for xx in range(x0 + inset, x1 - inset):
                    grid[yy][xx] = idx
        self._grid = grid
        self._bounds = bounds

        labels: dict[int, list[tuple[int, int, str]]] = {}
        for idx, (x0, y0, x1, y1) in bounds.items():
            rw, rh = x1 - x0, y1 - y0
            if rw < 6 or rh < 3:
                continue
            inset = 1 if (rw >= 3 and rh >= 3) else 0
            avail = rw - 2 * inset - 1
            if avail < 3:
                continue
            item = self._items[idx]
            name = item["name"]
            name_text = name if len(name) <= avail else name[: max(1, avail - 1)] + "\u2026"
            lines = [(y0 + inset, x0 + inset + 1, name_text)]
            if rh - 2 * inset >= 3:
                bt = human(item["bytes"])
                if len(bt) <= avail:
                    lines.append((y0 + inset + 1, x0 + inset + 1, bt))
            labels[idx] = lines
        self._labels = labels

    def render_line(self, y: int) -> Strip:
        self._ensure_layout()
        width = self.size.width
        if not self._grid or y >= len(self._grid):
            return Strip.blank(width)

        row = self._grid[y]
        segments = []
        cursor_bounds = self._bounds.get(self._cursor)
        cursor_color = (family_color(self._items[self._cursor].get("_family", "other"))
                         if 0 <= self._cursor < len(self._items) else None)

        for x in range(width):
            # Selection border overlay: the border ring sits on the outer
            # bounds of the selected rect, which the fill grid marks as
            # gutter (-1) once inset -- so this must be checked before the
            # -1 short-circuit below, using the rect's own bounds/color
            # rather than the grid's per-cell owner.
            if cursor_bounds:
                bx0, by0, bx1, by1 = cursor_bounds
                if bx0 <= x < bx1 and by0 <= y < by1:
                    big_enough = (bx1 - bx0) >= 2 and (by1 - by0) >= 2
                    on_edge_row = y in (by0, by1 - 1)
                    on_edge_col = x in (bx0, bx1 - 1)
                    if big_enough and (on_edge_row or on_edge_col):
                        if on_edge_row and on_edge_col:
                            ch = "+"
                        elif on_edge_row:
                            ch = "\u2500"
                        else:
                            ch = "\u2502"
                        segments.append((ch, Style(bgcolor=cursor_color, color="#ffffff", bold=True)))
                        continue

            idx = row[x]
            if idx == -1:
                segments.append((" ", Style(bgcolor=GUTTER_COLOR)))
                continue

            item = self._items[idx]
            color = family_color(item.get("_family", "other"))
            ch = " "
            style = Style(bgcolor=color, color=LABEL_TEXT_COLOR)

            for (ly, lx, text) in self._labels.get(idx, ()):
                if y == ly and lx <= x < lx + len(text):
                    ch = text[x - lx]
                    style = Style(bgcolor=color, color=LABEL_TEXT_COLOR, bold=True)

            segments.append((ch, style))

        from rich.segment import Segment
        return Strip([Segment(ch, style) for ch, style in segments])

    def on_click(self, event) -> None:
        self._ensure_layout()
        if not self._grid:
            return
        x, y = int(event.x), int(event.y)
        if 0 <= y < len(self._grid) and 0 <= x < len(self._grid[0]):
            idx = self._grid[y][x]
            if idx >= 0:
                self.post_message(self.BlockClicked(idx))


class NaviDuApp(App):
    CSS = """
    Screen { background: #05061a; }
    #bezel { height: 12; border: round #3a3fa0; background: #0d1030; padding: 0 1; }
    #navi { width: 19; height: 10; margin: 1 2 0 0; }
    #titleblock { width: 1fr; color: #eef6ff; padding-top: 1; }
    #runok { width: 14; height: 3; border: round #3dffb0; color: #3dffb0;
             content-align: center middle; text-style: bold; margin-top: 2; }
    #runok.bug { color: #ff4d6d; border: round #ff4d6d; }
    #main { height: 1fr; }
    #ownedlist { width: 34; border: round #3a3fa0; background: #0a0c28; }
    #memmap { width: 1fr; border: round #5a4ee0; background: #170f3a; }
    #infopanel { width: 36; border: round #3a3fa0; background: #0a0c28; padding: 1; }
    #bottombar { height: 4; }
    #hpwrap, #gaugewrap { width: 1fr; border: round #3a3fa0; margin: 0 1; padding: 0 1; }
    #hpbar, #gaugebar { width: 1fr; }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("backspace", "go_back", "Back"),
        Binding("r", "rescan", "Rescan"),
        Binding("q", "quit", "Quit"),
    ]

    cursor: reactive[int] = reactive(0)

    def __init__(self, quick: bool = False, auto_scan: bool = True):
        super().__init__()
        self.quick = quick
        self.auto_scan = auto_scan
        self.stack: list[Layer] = [Layer("ROOT", [])]
        self.roots_meta: list[dict] = []
        self.roots_total = 0
        self.roots_done = 0
        self.scanning = True
        self.had_errors = False
        self.error_count = 0
        self.drive = "C:\\"
        self.drive_used = 0
        self.drive_total = 1
        self._current_items: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="bezel"):
                yield NaviSprite(id="navi")
                yield Static(id="titleblock")
                yield Static("...", id="runok")
            with Horizontal(id="main"):
                yield OptionList(id="ownedlist")
                yield MemoryMap(id="memmap")
                yield Static(id="infopanel")
            with Horizontal(id="bottombar"):
                with Vertical(id="hpwrap"):
                    yield Static("HP (drive capacity)", classes="meterlabel")
                    yield ProgressBar(id="hpbar", total=100, show_eta=False)
                with Vertical(id="gaugewrap"):
                    yield Static("CUSTOM GAUGE (scan progress)", classes="meterlabel")
                    yield ProgressBar(id="gaugebar", total=100, show_eta=False)
        yield Footer()

    def on_mount(self) -> None:
        self.drive, self.drive_used, self.drive_total = drive_usage()
        self.query_one("#hpbar", ProgressBar).update(total=100, progress=self.drive_used / self.drive_total * 100)
        self.query_one("#ownedlist", OptionList).focus()
        self.refresh_chrome()
        self.refresh_layer()
        self.set_interval(3.2, self._toggle_blink)
        if self.auto_scan:
            self.run_scan()

    def _toggle_blink(self) -> None:
        sprite = self.query_one("#navi", NaviSprite)
        sprite.blink = True
        self.set_timer(0.18, lambda: setattr(sprite, "blink", False))

    # ---------------- scanning (background thread) ----------------

    @work(thread=True)
    def run_scan(self) -> None:
        roots_meta = default_roots(self.quick)
        self.call_from_thread(self._on_scan_started, len(roots_meta))
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(scan_root, m) for m in roots_meta]
            for fut in as_completed(futures):
                self.call_from_thread(self._on_root_scanned, fut.result())
        if not self.quick:
            for w in find_wsl_vhdx():
                r = {"name": f"WSL: {w['name']}", "path": w["path"], "family": "wsl",
                     "bytes": w["bytes"], "errors": 0, "children": []}
                self.call_from_thread(self._on_root_scanned, r)
        self.call_from_thread(self._on_scan_finished)

    def _on_scan_started(self, total: int) -> None:
        self.roots_total = total
        self.scanning = True
        self.refresh_chrome()

    def _on_root_scanned(self, r: dict) -> None:
        self.roots_meta.append(r)
        self.roots_done += 1
        if r["errors"] > 0:
            self.had_errors = True
            self.error_count += r["errors"]
        self.stack[0].items = sorted(self.roots_meta, key=lambda x: -x["bytes"])
        if len(self.stack) == 1:
            self.refresh_layer()
        self.refresh_chrome()

    def _on_scan_finished(self) -> None:
        self.scanning = False
        self.refresh_chrome()

    # ---------------- layer / selection state ----------------

    def display_items(self) -> list[dict]:
        """Sorted items for the current layer, capped both by count and by a
        minimum share of the view -- a long tail of sub-2% folders would
        otherwise render as illegible one-character slivers in a squarified
        grid, so it gets folded into a single "(+N more)" block instead."""
        layer = self.stack[-1]
        items = sorted(layer.items, key=lambda i: -i.get("bytes", 0))
        total = sum(i.get("bytes", 0) for i in items) or 1
        decorated = []
        for it in items:
            fam = it.get("family") or layer.family or "other"
            it2 = dict(it)
            it2["_family"] = fam
            decorated.append(it2)

        head, tail = [], []
        for it in decorated:
            if len(head) < MAX_TUI_BLOCKS - 1 and it["bytes"] / total >= MIN_BLOCK_SHARE:
                head.append(it)
            else:
                tail.append(it)
        if tail:
            head.append({"name": f"(+{len(tail)} more)", "path": "",
                          "bytes": sum(i["bytes"] for i in tail), "_family": "other", "children": []})
        return head

    def refresh_layer(self) -> None:
        items = self.display_items()
        self._current_items = items

        opts = self.query_one("#ownedlist", OptionList)
        opts.clear_options()
        for it in items:
            line = Text()
            line.append("\u25cf ", style=family_color(it["_family"]))
            line.append(it["name"])
            line.append(f"  {human(it['bytes'])}", style="dim")
            opts.add_option(Option(line))

        self.cursor = min(self.cursor, max(0, len(items) - 1))
        opts.highlighted = self.cursor if items else None

        self.query_one("#memmap", MemoryMap).set_items(items, self.cursor)
        self.sub_title = " \u25b8 ".join(l.label for l in self.stack)
        self.update_info()

    def watch_cursor(self, value: int) -> None:
        self.query_one("#memmap", MemoryMap).set_cursor(value)
        self.update_info()

    def update_info(self) -> None:
        panel = self.query_one("#infopanel", Static)
        items = self._current_items
        text = Text()
        text.append("PROGRAM INFORMATION\n", style="bold #8f97c9")
        text.append(("\u25b8 ".join(l.label for l in self.stack)) + "\n\n", style="dim")
        if not items or self.cursor >= len(items):
            text.append("Scanning...\n" if self.scanning else "Empty.\n", style="dim")
        else:
            it = items[self.cursor]
            pct_drive = it["bytes"] / self.drive_total * 100
            total_view = sum(i["bytes"] for i in items) or 1
            pct_view = it["bytes"] / total_view * 100
            text.append(it["name"] + "\n", style="bold")
            if it.get("path"):
                text.append(it["path"] + "\n", style="dim")
            text.append("\n")
            text.append(f"Bytes:       {human(it['bytes'])}\n")
            text.append(f"% of drive:  {pct_drive:.2f}%\n")
            text.append(f"% of view:   {pct_view:.1f}%\n")
            text.append(f"Family:      {FAMILIES.get(it['_family'], FAMILIES['other'])['label']}\n")
            if it.get("children"):
                text.append("\n[Enter] drill in\n", style="dim italic")
        if len(self.stack) > 1:
            text.append("\n[Esc] back up\n", style="dim italic")
        panel.update(text)

    def refresh_chrome(self) -> None:
        title = self.query_one("#titleblock", Static)
        status_line = "scanning..." if self.scanning else f"scan complete \u00b7 {self.roots_done} roots"
        title.update(Text.from_markup(
            f"[bold]NAVI-DU[/]\n[dim]{os.environ.get('COMPUTERNAME','?')} \u00b7 "
            f"{self.drive} {human(self.drive_used)}/{human(self.drive_total)} used \u00b7 {status_line}[/]"
        ))
        runok = self.query_one("#runok", Static)
        if self.scanning:
            runok.update("...")
            runok.remove_class("bug")
        elif self.had_errors:
            runok.update("BUG")
            runok.add_class("bug")
            runok.tooltip = f"{self.error_count} paths were access-denied during the scan"
        else:
            runok.update("OK!")
            runok.remove_class("bug")
        gauge = self.query_one("#gaugebar", ProgressBar)
        pct = (self.roots_done / self.roots_total * 100) if self.roots_total else 0
        gauge.update(total=100, progress=pct)

    # ---------------- interaction ----------------

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_index is not None:
            self.cursor = event.option_index

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.select_index(event.option_index)
        self.drill(event.option_index)

    def on_memory_map_block_clicked(self, message: MemoryMap.BlockClicked) -> None:
        self.select_index(message.idx)
        self.drill(message.idx)

    def select_index(self, idx: int) -> None:
        self.cursor = idx
        self.query_one("#ownedlist", OptionList).highlighted = idx

    def drill(self, idx: int | None) -> None:
        if idx is None or idx >= len(self._current_items):
            return
        item = self._current_items[idx]
        if item.get("children"):
            self.stack.append(Layer(item["name"], item["children"], item.get("_family")))
            self.cursor = 0
            self.refresh_layer()

    def action_go_back(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()
            self.cursor = 0
            self.refresh_layer()

    def action_rescan(self) -> None:
        self.stack = [Layer("ROOT", [])]
        self.roots_meta = []
        self.roots_done = 0
        self.roots_total = 0
        self.had_errors = False
        self.error_count = 0
        self.cursor = 0
        self.refresh_layer()
        self.run_scan()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="scan only AppData\\Local + code\\ (fast)")
    args = ap.parse_args()
    NaviDuApp(quick=args.quick).run()


if __name__ == "__main__":
    main()

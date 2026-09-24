"""CMD Center follows light themes (Paper) instead of a fixed black HUD."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_theme_marks_light_luma_for_paper_background():
    theme = (ROOT / "static" / "js" / "theme.js").read_text(encoding="utf-8")
    assert "function markThemeLuma" in theme
    assert "dataset.themeLuma" in theme
    apply = theme.split("export function applyColors", 1)[1][:400]
    assert "markThemeLuma" in apply
    paper = theme.split("paper:", 1)[1].split("},", 1)[0]
    assert "#faf8f5" in paper


def test_early_paint_sets_theme_luma():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "dataset.themeLuma" in html


def test_cmd_center_light_palette_overrides_phosphor_hud():
    cmd = (ROOT / "static" / "js" / "cmdCenter.js").read_text(encoding="utf-8")
    assert 'html[data-theme-luma="light"] .cmd-center-root' in cmd
    assert "--cmd-bg: var(--bg)" in cmd
    assert "--cmd-ink: var(--fg)" in cmd
    assert "--cmd-scan-blend: multiply" in cmd
    assert "background: var(--cmd-bg)" in cmd
    assert "color: var(--cmd-ink)" in cmd


def test_cmd_scene_uses_ink_on_light_luma():
    scene = (ROOT / "static" / "js" / "cmdCenterScene.js").read_text(encoding="utf-8")
    assert "function _isLightVault" in scene
    assert "function _sceneTone" in scene
    assert "dataset.themeLuma === 'light'" in scene

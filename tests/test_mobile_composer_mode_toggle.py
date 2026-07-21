"""Pin mobile composer Agent/Chat visibility + Web/Shell overflow collapse.

On phones the Agent/Chat toggle must stay visible (override the narrow
chatbar container hide), and Web/Shell park in the + overflow menu so the
bottom row stays uncluttered.
"""
from pathlib import Path


CSS = Path("static/style.css").read_text(encoding="utf-8")
APP_JS = Path("static/app.js").read_text(encoding="utf-8")


def test_mobile_media_reshows_mode_toggle():
    assert "@container chatbar (max-width: 340px)" in CSS
    assert ".chat-input-right .mode-toggle { display: none !important; }" in CSS
    # Mobile override must win so Agent/Chat stays available on phones.
    assert ".chat-input-right .mode-toggle {\n        display: flex !important;\n      }" in CSS
    mobile_idx = CSS.find("@media (max-width:768px)")
    override_idx = CSS.find(".chat-input-right .mode-toggle {\n        display: flex !important;\n      }")
    assert mobile_idx != -1 and override_idx != -1
    assert override_idx > mobile_idx


def test_toolbar_overflow_force_collapses_on_mobile():
    assert "const _mobileComposer = window.innerWidth <= 768;" in APP_JS
    assert "if ((_researchOn && _docViewOn) || _mobileComposer)" in APP_JS
    assert "collapsibleIds = ['bash-toggle-btn', 'web-toggle-btn']" in APP_JS

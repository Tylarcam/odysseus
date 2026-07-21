"""Pin selection → Generate Prompt draft builder + <code> wrapper contract.

The Gen menu preview must be <pre><code>…</code></pre> so chat's global
.edit-code handler (which requires a <code> child) can toggle contentEditable.
A bare <pre> with textContent made the pencil button a silent no-op.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SRC = (_REPO / "static" / "js" / "selectionPromptGen.js").read_text(encoding="utf-8")
_HAS_NODE = shutil.which("node") is not None


def _pure_helpers_src() -> str:
    """Strip ESM imports/exports so Node can eval the pure helpers without ui.js."""
    body = _SRC
    body = re.sub(r"^import .+?;\n", "", body, flags=re.M)
    body = body.replace("export function buildPromptDraft", "function buildPromptDraft")
    body = body.replace("export function openGenTargetMenu", "function openGenTargetMenu")
    # Drop openGenTargetMenu (needs DOM); keep buildPromptDraft + _contextLine.
    cut = body.find("function _livePromptText")
    if cut == -1:
        cut = body.find("function openGenTargetMenu")
    assert cut > 0, "expected openGenTargetMenu / _livePromptText in source"
    return body[:cut]


def _run(body: str) -> str:
    js = _pure_helpers_src() + "\n" + body
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, encoding="utf-8",
        cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_build_prompt_draft_includes_selection_and_needed_placeholders():
    body = r"""
    const draft = buildPromptDraft('Ship the Gen edit button', { label: 'Odysseus selection' });
    console.log(JSON.stringify({
      hasRole: draft.includes('# Role'),
      hasObjective: draft.includes('Ship the Gen edit button'),
      hasContext: draft.includes('Source: Odysseus selection'),
      hasNeeded: draft.includes('[NEEDED:'),
      quoted: draft.includes('> Ship the Gen edit button'),
    }));
    """
    out = json.loads(_run(body))
    assert out == {
        "hasRole": True,
        "hasObjective": True,
        "hasContext": True,
        "hasNeeded": True,
        "quoted": True,
    }


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_source_file_uses_code_wrapper_for_preview():
    """Regression: preview must ship a <code> child for Edit to work."""
    assert '<pre class="selection-gen-preview"><code></code></pre>' in _SRC
    assert "codeEl.textContent = draft" in _SRC
    assert "_livePromptText(pre, draft)" in _SRC

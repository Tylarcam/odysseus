"""Pin Phase-1 writing assist helpers (static/js/writingAssist.js).

Driven through `node --input-type=module` so we exercise the real JS without a
full Vitest/Jest setup (same approach as test_composer_arrow_up_recall_js.py).
Skips when `node` is not installed rather than failing.

Locks in: issue normalization, vocabulary filter (spelling-only), range
validation / apply safety, debounce + max-length constants, silent degrade
when Harper import fails, and teardown discarding stale results.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HELPER = _REPO / "static" / "js" / "writingAssist.js"
_HELPER_URL = _HELPER.as_uri()
_HAS_NODE = shutil.which("node") is not None


def _run_js(source: str) -> dict | list:
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_normalize_issue_shape_and_categories():
    js = f"""
    import {{
      normalizeIssue,
      categorizeLintKind,
    }} from '{_HELPER_URL}';

    const cases = [
      {{ start: 0, end: 3, message: 'Unknown word', suggestions: ['the'], lint_kind: 'Spelling' }},
      {{ start: 2, end: 4, message: 'Wrong article', suggestions: ['an'], category: 'grammar' }},
      {{ start: 1, end: 5, message: 'Wordy', suggestions: ['x'], lint_kind: 'Style' }},
      {{ start: -1, end: 2, message: 'bad', suggestions: [] }},
      {{ start: 0, end: 1, message: '', suggestions: ['a'] }},
    ];
    console.log(JSON.stringify({{
      kinds: ['Spelling', 'Capitalization', 'Readability'].map(categorizeLintKind),
      normalized: cases.map(normalizeIssue),
    }}));
    """
    out = _run_js(js)
    assert out["kinds"] == ["spelling", "grammar", "style"]
    assert out["normalized"][0] == {
        "start": 0,
        "end": 3,
        "message": "Unknown word",
        "suggestions": ["the"],
        "category": "spelling",
    }
    assert out["normalized"][1]["category"] == "grammar"
    assert out["normalized"][2]["category"] == "style"
    assert out["normalized"][3] is None
    assert out["normalized"][4] is None


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_vocabulary_filters_spelling_only():
    js = f"""
    import {{
      filterIssuesByVocabulary,
      addCustomVocabularyWord,
      loadCustomVocabulary,
      normalizeVocabToken,
    }} from '{_HELPER_URL}';

    const store = {{ data: {{}}, getItem(k) {{ return this.data[k] ?? null; }}, setItem(k, v) {{ this.data[k] = String(v); }} }};
    const text = 'Odysseus sailed to Ithaca';
    addCustomVocabularyWord('Odysseus', store, {{ syncPrefs: false }});
    addCustomVocabularyWord('  ITHACA ', store, {{ syncPrefs: false }});
    const vocab = loadCustomVocabulary(store);

    const issues = [
      {{ start: 0, end: 8, message: 'Unknown', suggestions: [], category: 'spelling' }},
      {{ start: 19, end: 25, message: 'Unknown', suggestions: [], category: 'spelling' }},
      {{ start: 9, end: 15, message: 'Style note', suggestions: ['went'], category: 'style' }},
      {{ start: 0, end: 8, message: 'Grammar', suggestions: [], category: 'grammar' }},
    ];
    console.log(JSON.stringify({{
      tokens: vocab.words.map(normalizeVocabToken),
      filtered: filterIssuesByVocabulary(issues, vocab.words, text).map(i => i.category + ':' + i.message),
    }}));
    """
    out = _run_js(js)
    assert out["tokens"] == ["odysseus", "ithaca"]
    # Spelling hits for Odysseus/Ithaca suppressed; style + grammar kept; spelling
    # for Odysseus at 0..8 suppressed, Ithaca at 19..25 suppressed.
    assert out["filtered"] == ["style:Style note", "grammar:Grammar"]


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_apply_validates_ranges_and_refuses_stale_slices():
    js = f"""
    import {{
      validateIssueRange,
      applyIssueReplacement,
    }} from '{_HELPER_URL}';

    const text = 'This is an test';
    const issue = {{ start: 8, end: 10 }};
    console.log(JSON.stringify({{
      ok: validateIssueRange(text, issue, 'an'),
      applied: applyIssueReplacement(text, issue, 'a', 'an'),
      stale: applyIssueReplacement(text, issue, 'a', 'xx'),
      oob: applyIssueReplacement(text, {{ start: 0, end: 99 }}, 'x'),
    }}));
    """
    out = _run_js(js)
    assert out["ok"] is True
    assert out["applied"] == "This is a test"
    assert out["stale"] is None
    assert out["oob"] is None


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_constants_and_wire_silent_degrade():
    js = f"""
    import {{
      DEBOUNCE_MS,
      MAX_TEXT_LENGTH,
      VOCAB_STORAGE_KEY,
      wireWritingAssist,
    }} from '{_HELPER_URL}';

    const listeners = new Map();
    const textarea = {{
      value: 'teh',
      _writingAssistWired: false,
      hasAttribute(name) {{ return name === 'spellcheck' || name === 'lang'; }},
      getAttribute(name) {{ return name === 'lang' ? 'en' : name === 'spellcheck' ? 'true' : null; }},
      setAttribute() {{}},
      closest() {{ return null; }},
      insertAdjacentElement() {{}},
      addEventListener(type, fn) {{
        if (!listeners.has(type)) listeners.set(type, []);
        listeners.get(type).push(fn);
      }},
      removeEventListener(type, fn) {{
        const arr = listeners.get(type) || [];
        listeners.set(type, arr.filter(f => f !== fn));
      }},
      dispatchEvent() {{ return true; }},
    }};

    const docListeners = new Map();
    const created = [];
    const doc = {{
      head: {{ appendChild(n) {{ created.push(['head', n]); }} }},
      documentElement: {{}},
      getElementById() {{ return null; }},
      createElement(tag) {{
        const el = {{
          tagName: tag.toUpperCase(),
          style: {{}},
          children: [],
          attributes: {{}},
          hidden: false,
          textContent: '',
          className: '',
          id: '',
          setAttribute(k, v) {{ this.attributes[k] = v; }},
          getAttribute(k) {{ return this.attributes[k]; }},
          appendChild(c) {{ this.children.push(c); }},
          replaceChildren(...c) {{ this.children = c; }},
          addEventListener(type, fn) {{
            if (!this._l) this._l = new Map();
            if (!this._l.has(type)) this._l.set(type, []);
            this._l.get(type).push(fn);
          }},
          removeEventListener(type, fn) {{
            if (!this._l) return;
            this._l.set(type, (this._l.get(type) || []).filter(f => f !== fn));
          }},
          querySelector() {{ return null; }},
          contains() {{ return false; }},
          focus() {{}},
          remove() {{}},
        }};
        created.push(['el', tag]);
        return el;
      }},
      addEventListener(type, fn) {{
        if (!docListeners.has(type)) docListeners.set(type, []);
        docListeners.get(type).push(fn);
      }},
      removeEventListener(type, fn) {{
        docListeners.set(type, (docListeners.get(type) || []).filter(f => f !== fn));
      }},
    }};

    const handle = wireWritingAssist(textarea, {{
      document: doc,
      importHarper: async () => {{ throw new Error('boom'); }},
    }});

    // Force an immediate check (bypass debounce) and confirm silent empty result.
    await handle.checkNow();
    const afterFail = {{
      available: handle.isAvailable(),
      issues: handle.getIssues(),
    }};
    handle.destroy();
    console.log(JSON.stringify({{
      debounce: DEBOUNCE_MS,
      maxLen: MAX_TEXT_LENGTH,
      vocabKey: VOCAB_STORAGE_KEY,
      afterFail,
      destroyedWired: textarea._writingAssistWired,
      inputListeners: (listeners.get('input') || []).length,
    }}));
    """
    out = _run_js(js)
    assert 600 <= out["debounce"] <= 900
    assert out["maxLen"] == 8000
    assert out["vocabKey"].startswith("odysseus.writingAssist.vocab.")
    assert out["afterFail"] == {"available": False, "issues": []}
    assert out["destroyedWired"] is False
    assert out["inputListeners"] == 0


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_oversized_text_skips_without_error():
    js = f"""
    import {{ MAX_TEXT_LENGTH, wireWritingAssist }} from '{_HELPER_URL}';

    let lintCalls = 0;
    const fakeLinter = {{
      async setup() {{}},
      async lint() {{ lintCalls += 1; return []; }},
      async importWords() {{}},
      async dispose() {{}},
    }};

    const listeners = new Map();
    const textarea = {{
      value: 'x'.repeat(MAX_TEXT_LENGTH + 1),
      _writingAssistWired: false,
      hasAttribute() {{ return true; }},
      getAttribute() {{ return 'en'; }},
      setAttribute() {{}},
      closest() {{ return null; }},
      insertAdjacentElement() {{}},
      addEventListener(type, fn) {{
        if (!listeners.has(type)) listeners.set(type, []);
        listeners.get(type).push(fn);
      }},
      removeEventListener(type, fn) {{
        listeners.set(type, (listeners.get(type) || []).filter(f => f !== fn));
      }},
      dispatchEvent() {{ return true; }},
    }};
    const doc = {{
      head: {{ appendChild() {{}} }},
      documentElement: {{}},
      getElementById() {{ return null; }},
      createElement(tag) {{
        return {{
          tagName: tag,
          style: {{}},
          children: [],
          attributes: {{}},
          hidden: false,
          textContent: '',
          className: '',
          id: '',
          setAttribute(k, v) {{ this.attributes[k] = v; }},
          appendChild(c) {{ this.children.push(c); }},
          replaceChildren(...c) {{ this.children = c; }},
          addEventListener() {{}},
          removeEventListener() {{}},
          querySelector() {{ return null; }},
          contains() {{ return false; }},
          focus() {{}},
          remove() {{}},
        }};
      }},
      addEventListener() {{}},
      removeEventListener() {{}},
    }};

    const handle = wireWritingAssist(textarea, {{
      document: doc,
      importHarper: async () => ({{
        WorkerLinter: class {{ constructor() {{ return fakeLinter; }} }},
        slimBinary: {{}},
      }}),
    }});
    await handle.checkNow();
    console.log(JSON.stringify({{ lintCalls, issues: handle.getIssues().length }}));
    handle.destroy();
    """
    out = _run_js(js)
    assert out == {"lintCalls": 0, "issues": 0}


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_stale_results_discarded_by_cancellation_token():
    js = f"""
    import {{ wireWritingAssist }} from '{_HELPER_URL}';

    let resolveLint;
    const lintPromise = new Promise((resolve) => {{ resolveLint = resolve; }});
    const fakeLinter = {{
      async setup() {{}},
      async lint(text) {{
        await lintPromise;
        return [{{
          span() {{ return {{ start: 0, end: 3 }}; }},
          message() {{ return 'stale-' + text; }},
          lint_kind() {{ return 'Spelling'; }},
          suggestions() {{ return []; }},
          get_problem_text() {{ return text.slice(0, 3); }},
          free() {{}},
        }}];
      }},
      async importWords() {{}},
      async dispose() {{}},
    }};

    const textarea = {{
      value: 'aaa',
      _writingAssistWired: false,
      hasAttribute() {{ return true; }},
      getAttribute() {{ return 'en'; }},
      setAttribute() {{}},
      closest() {{ return null; }},
      insertAdjacentElement() {{}},
      addEventListener() {{}},
      removeEventListener() {{}},
      dispatchEvent() {{ return true; }},
    }};
    const doc = {{
      head: {{ appendChild() {{}} }},
      documentElement: {{}},
      getElementById() {{ return null; }},
      createElement(tag) {{
        return {{
          tagName: tag,
          style: {{}},
          children: [],
          attributes: {{}},
          hidden: false,
          textContent: '',
          className: '',
          id: '',
          setAttribute(k, v) {{ this.attributes[k] = v; }},
          appendChild(c) {{ this.children.push(c); }},
          replaceChildren(...c) {{ this.children = c; }},
          addEventListener() {{}},
          removeEventListener() {{}},
          querySelector() {{ return null; }},
          contains() {{ return false; }},
          focus() {{}},
          remove() {{}},
        }};
      }},
      addEventListener() {{}},
      removeEventListener() {{}},
    }};

    const handle = wireWritingAssist(textarea, {{
      document: doc,
      importHarper: async () => ({{
        WorkerLinter: class {{ constructor() {{ return fakeLinter; }} }},
        slimBinary: {{}},
      }}),
    }});

    const p1 = handle.checkNow();
    textarea.value = 'bbb';
    const p2 = handle.checkNow();
    resolveLint();
    await Promise.all([p1, p2]);
    console.log(JSON.stringify({{ issues: handle.getIssues() }}));
    handle.destroy();
    """
    out = _run_js(js)
    # Only the latest generation should remain (bbb), not stale aaa.
    assert len(out["issues"]) == 1
    assert out["issues"][0]["message"] == "stale-bbb"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_vocab_prefs_sync_merge_and_clear():
    """Phase 2: localStorage ↔ prefs mapping + fire-and-forget PUT."""
    js = f"""
    import {{
      VOCAB_PREFS_KEY,
      VOCAB_STORAGE_KEY,
      MAX_VOCAB_WORDS,
      addCustomVocabularyWord,
      clearCustomVocabulary,
      loadCustomVocabulary,
      mergeVocabWordLists,
      prefsValueToVocabWords,
      removeCustomVocabularyWord,
      syncCustomVocabularyFromPrefs,
    }} from '{_HELPER_URL}';

    const store = {{ data: {{}}, getItem(k) {{ return this.data[k] ?? null; }}, setItem(k, v) {{ this.data[k] = String(v); }} }};
    const puts = [];
    const fetchMock = async (url, opts = {{}}) => {{
      if ((opts.method || 'GET') === 'PUT') {{
        puts.push({{ url, body: JSON.parse(opts.body) }});
        return {{ ok: true, json: async () => ({{ key: VOCAB_PREFS_KEY, value: JSON.parse(opts.body).value }}) }};
      }}
      return {{
        ok: true,
        json: async () => ({{ key: VOCAB_PREFS_KEY, value: ['ServerWord', 'odysseus'] }}),
      }};
    }};

    addCustomVocabularyWord('Odysseus', store, {{ fetch: fetchMock }});
    const merged = await syncCustomVocabularyFromPrefs({{ fetch: fetchMock, storage: store }});
    removeCustomVocabularyWord('ServerWord', store, {{ fetch: fetchMock }});
    clearCustomVocabulary(store, {{ fetch: fetchMock }});

    console.log(JSON.stringify({{
      prefsKey: VOCAB_PREFS_KEY,
      storageKey: VOCAB_STORAGE_KEY,
      maxWords: MAX_VOCAB_WORDS,
      prefsShape: prefsValueToVocabWords(['A', 'a', 'B']),
      objectShape: prefsValueToVocabWords({{ version: 1, words: ['X'] }}),
      union: mergeVocabWordLists(['Local'], ['local', 'Remote']),
      afterMerge: merged.words,
      afterClear: loadCustomVocabulary(store).words,
      putBodies: puts.map(p => p.body.value),
      putUrls: puts.map(p => p.url),
    }}));
    """
    out = _run_js(js)
    assert out["prefsKey"] == "writing_dictionary_words"
    assert out["storageKey"].startswith("odysseus.writingAssist.vocab.")
    assert out["maxWords"] == 500
    assert out["prefsShape"] == ["A", "B"]
    assert out["objectShape"] == ["X"]
    assert out["union"] == ["Local", "Remote"]
    assert out["afterMerge"] == ["Odysseus", "ServerWord"]
    assert out["afterClear"] == []
    # add → sync merge PUT (local-only Odysseus) → remove PUT → clear PUT []
    assert out["putUrls"] and all(u.endswith("/api/prefs/writing_dictionary_words") for u in out["putUrls"])
    assert [] in out["putBodies"]
    assert any("Odysseus" in (body or []) for body in out["putBodies"])

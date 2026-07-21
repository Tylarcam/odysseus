"""Exercise static/js/emailLibrary/localSearch.js via node --input-type=module."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HELPER = _REPO / "static" / "js" / "emailLibrary" / "localSearch.js"
_HAS_NODE = shutil.which("node") is not None


def _run(js: str) -> str:
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", js],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


SAMPLE = [
    {
        "uid": "1",
        "message_id": "<a@x.com>",
        "subject": "Meeting follow-up",
        "from_name": "Esther Grassian",
        "from_address": "esther@stanford.edu",
        "date_epoch": 1000,
    },
    {
        "uid": "2",
        "message_id": "<b@x.com>",
        "subject": "Invoice",
        "from_name": "Bob Smith",
        "from_address": "bob@example.com",
        "date_epoch": 2000,
    },
]


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_fuzzy_search_matches_display_name():
    js = f"""
    import {{ searchEmailCorpus, buildEmailSearchCorpus }} from './static/js/emailLibrary/localSearch.js';
    const corpus = buildEmailSearchCorpus({{ emails: {json.dumps(SAMPLE)} }});
    const hits = searchEmailCorpus('Esther Grassian', corpus);
    console.log(JSON.stringify(hits.map(h => h.uid)));
    """
    uids = json.loads(_run(js))
    assert uids == ["1"]


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_fuzzy_search_partial_token():
    js = f"""
    import {{ searchEmailCorpus, buildEmailSearchCorpus }} from './static/js/emailLibrary/localSearch.js';
    const corpus = buildEmailSearchCorpus({{ emails: {json.dumps(SAMPLE)} }});
    const hits = searchEmailCorpus('Grassian', corpus);
    console.log(JSON.stringify(hits.map(h => h.uid)));
    """
    uids = json.loads(_run(js))
    assert uids == ["1"]


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_corpus_dedupes_by_message_id():
    js = f"""
    import {{ buildEmailSearchCorpus, emailSearchKey }} from './static/js/emailLibrary/localSearch.js';
    const dup = {json.dumps(SAMPLE[0])};
    const corpus = buildEmailSearchCorpus({{ emails: [dup, dup, dup] }});
    console.log(JSON.stringify([corpus.length, emailSearchKey(dup)]));
    """
    length, key = json.loads(_run(js))
    assert length == 1
    assert key.startswith("mid:")


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_short_query_returns_empty():
    js = f"""
    import {{ searchEmailCorpus, buildEmailSearchCorpus }} from './static/js/emailLibrary/localSearch.js';
    const corpus = buildEmailSearchCorpus({{ emails: {json.dumps(SAMPLE)} }});
    console.log(JSON.stringify(searchEmailCorpus('E', corpus).length));
    """
    assert json.loads(_run(js)) == 0

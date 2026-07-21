"""Fenced ```list_emails``` blocks must remap to mcp__email__* like native calls."""

import json
import sys
from unittest.mock import MagicMock

_ABSENT = object()
_AGENT_MODULES = ["src.agent_tools", "src.tool_parsing", "src.tool_schemas"]
_STUBBED = [
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.ext", "sqlalchemy.ext.declarative",
    "sqlalchemy.ext.hybrid", "sqlalchemy.sql", "sqlalchemy.sql.expression",
    "src.database", "core.models", "core.database", "core.auth",
]
_saved_stubs = {name: sys.modules.get(name, _ABSENT) for name in _STUBBED}

for _mod in _AGENT_MODULES:
    sys.modules.pop(_mod, None)
for _mod in _STUBBED:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import src.agent_tools  # noqa: E402,F401
from src.tool_parsing import parse_tool_blocks  # noqa: E402

for _name, _original in _saved_stubs.items():
    if _original is _ABSENT:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _original


def test_fenced_list_emails_remapped_to_mcp_email():
    text = '```list_emails\n{"folder": "INBOX", "max_results": 20, "account": "gmail"}\n```'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "mcp__email__list_emails"
    args = json.loads(blocks[0].content)
    assert args["folder"] == "INBOX"
    assert args["max_results"] == 20


def test_fenced_manage_notes_still_works():
    text = '```manage_notes\n{"action": "list"}\n```'
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "manage_notes"
    assert json.loads(blocks[0].content)["action"] == "list"


def test_fenced_bash_stays_raw_text():
    text = "```bash\necho hello\n```"
    blocks = parse_tool_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].tool_type == "bash"
    assert blocks[0].content == "echo hello"

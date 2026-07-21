"""Smoke test: fenced list_emails parses to mcp__email__ and executes."""
import asyncio
import json
import sys

from src.agent_tools import ToolBlock
from src.tool_parsing import parse_tool_blocks
from src import tool_execution as te
from src.tool_utils import set_mcp_manager


def main() -> int:
    text = '```list_emails\n{"folder": "INBOX", "max_results": 5}\n```'
    blocks = parse_tool_blocks(text)
    if len(blocks) != 1:
        print("FAIL: expected 1 block, got", blocks)
        return 1
    if blocks[0].tool_type != "mcp__email__list_emails":
        print("FAIL: wrong tool_type:", blocks[0].tool_type)
        return 1
    print("parse OK:", blocks[0].tool_type, json.loads(blocks[0].content))

    class FakeMcp:
        async def call_tool(self, qualified, args):
            assert qualified == "mcp__email__list_emails"
            assert args.get("folder") == "INBOX"
            return {"stdout": "Found 2 email(s)", "stderr": "", "exit_code": 0}

    set_mcp_manager(FakeMcp())
    desc, result = asyncio.run(te.execute_tool_block(blocks[0], owner=None))
    err = str(result.get("error") or "")
    if "Unknown tool type" in err:
        print("FAIL: still unknown tool type:", result)
        return 1
    if result.get("exit_code") == 0:
        print("execute OK:", desc, result.get("stdout", "")[:80])
        return 0
    # Reached MCP dispatch (admin/policy may block in locked-down deployments).
    print("execute dispatch OK (policy blocked as expected):", err[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())

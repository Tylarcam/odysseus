"""Chat/agent/MCP manage_memory pin/unpin — same pin_memory_item as voice/HTTP."""

import json

import pytest

from src.agent_tools import ToolBlock  # noqa: F401 — load before tool_schemas
from src.chat_processor import ChatProcessor
from src.memory import (
    PIN_ORIGIN_AUTO_MONEY,
    PIN_ORIGIN_USER,
    MemoryManager,
    is_money_prosperity_fact,
    load_pinned_memory_facts,
    pin_memory_item,
)
from src.tool_schemas import FUNCTION_TOOL_SCHEMAS, function_call_to_tool_block


def _memory_schema():
    return next(s for s in FUNCTION_TOOL_SCHEMAS if s["function"]["name"] == "manage_memory")


def test_chat_manage_memory_schema_allows_pin_and_unpin():
    schema = _memory_schema()
    enum = schema["function"]["parameters"]["properties"]["action"]["enum"]
    for act in ("list", "add", "edit", "delete", "search", "pin", "unpin"):
        assert act in enum
    desc = (schema["function"].get("description") or "").lower()
    assert "pin" in desc
    assert "does not delete" in desc
    assert "memory_id" in schema["function"]["parameters"]["properties"]


def test_function_call_to_tool_block_encodes_pin_memory_id():
    block = function_call_to_tool_block(
        "manage_memory",
        json.dumps({"action": "pin", "memory_id": "probe-mem-1"}),
    )
    assert block is not None
    assert block.tool_type == "manage_memory"
    lines = block.content.strip().split("\n")
    assert lines[0] == "pin"
    assert lines[1] == "probe-mem-1"

    un = function_call_to_tool_block(
        "manage_memory",
        json.dumps({"action": "unpin", "memory_id": "probe-mem-1"}),
    )
    assert un.content.strip().split("\n")[:2] == ["unpin", "probe-mem-1"]


@pytest.mark.asyncio
async def test_do_manage_memory_pin_does_not_delete(tmp_path, monkeypatch):
    import src.ai_interaction as ai

    mgr = MemoryManager(str(tmp_path))
    entry = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    mgr.save([entry])
    monkeypatch.setattr(ai, "_memory_manager", mgr)
    monkeypatch.setattr(ai, "_memory_vector", None)

    pin_calls = []
    real_pin = __import__("src.memory", fromlist=["pin_memory_item"]).pin_memory_item

    def wrapped(memory_manager, memory_id, pinned=True, owner=None):
        pin_calls.append({"memory_id": memory_id, "pinned": pinned, "owner": owner})
        return real_pin(memory_manager, memory_id, pinned=pinned, owner=owner)

    monkeypatch.setattr("src.memory.pin_memory_item", wrapped)

    out = await ai.do_manage_memory(f"pin\n{entry['id']}", owner="tcam")
    assert "error" not in out
    assert out.get("pinned") is True
    assert "pinned" in (out.get("results") or "").lower()
    assert "deleted" not in (out.get("results") or "").lower()
    assert pin_calls and pin_calls[0]["pinned"] is True

    loaded = mgr.load_all()
    assert len(loaded) == 1
    assert loaded[0]["pinned"] is True
    assert loaded[0]["text"] == "Q3 retainer is $12k"

    pin_calls.clear()
    un = await ai.do_manage_memory(f"unpin\n{entry['id'][:8]}", owner="tcam")
    assert un.get("pinned") is False
    assert "unpinned" in (un.get("results") or "").lower()
    assert "deleted" not in (un.get("results") or "").lower()
    remaining = mgr.load_all()
    assert len(remaining) == 1
    assert remaining[0]["pinned"] is False
    assert remaining[0]["text"] == "Q3 retainer is $12k"


def test_load_pinned_memory_facts_pin_and_unpin(tmp_path):
    mgr = MemoryManager(str(tmp_path))
    money = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    other = mgr.add_entry("Prefers concise replies", category="preference", owner="tcam")
    mgr.save([money, other])

    assert money.get("pinned") is True
    assert not other.get("pinned")
    assert load_pinned_memory_facts(owner="tcam", memory_manager=mgr) == [
        "Q3 retainer is $12k"
    ]
    assert "Prefers concise replies" not in load_pinned_memory_facts(
        owner="tcam", memory_manager=mgr
    )

    pin_memory_item(mgr, money["id"], pinned=False, owner="tcam")
    assert load_pinned_memory_facts(owner="tcam", memory_manager=mgr) == []


def test_add_money_fact_auto_pins_generic_preference_does_not(tmp_path):
    mgr = MemoryManager(str(tmp_path))
    money = mgr.add_entry("Send pack logged as sent", owner="tcam")
    pref = mgr.add_entry("Prefers concise replies", category="preference", owner="tcam")
    grant = mgr.add_entry(
        "Vanier grant nomination packet is the live gate", owner="tcam"
    )
    invoice = mgr.add_entry("NPR invoice is unpaid", owner="tcam")
    mgr.save([money, pref, grant, invoice])

    assert is_money_prosperity_fact(money["text"]) is True
    assert is_money_prosperity_fact(pref["text"], "preference") is False
    assert money.get("pinned") is True
    assert grant.get("pinned") is True
    assert invoice.get("pinned") is True
    assert not pref.get("pinned")
    facts = load_pinned_memory_facts(owner="tcam", memory_manager=mgr)
    assert "Send pack logged as sent" in facts
    assert "Prefers concise replies" not in facts


_JOB_PREF_NOISE = (
    "Job & location preferences: Prioritizes revenue-generating AI consulting "
    "and GTM/Operations roles over teaching."
)
_FRUIT_IDS_NOISE = (
    "Swarm CANONICAL blackboard doc_id=30abbc6f. Fruit Ledger restored "
    "doc_id=f29c3b1d. Agents must append blackboard entries ONLY to the "
    "CANONICAL blackboard."
)
_ARCHIVE_NOISE = (
    "APPROVAL NEEDED: bulk-pipeline-cleanup — Archive all 44 paused job "
    "leads from revenue pipeline. User intent: archive all (not mark_applied)."
)
_TRIAGE_DOCKET = (
    "Odyssey Triage 2026-07-24: 5 Upwork proposals still unsent. "
    "NPR Panel 2 thank-yous ready to send."
)
_FRUIT_HARVEST = "FRUIT: $400 harvest from NPR panel"


def test_money_fact_matcher_skips_noise_pins_docket(tmp_path):
    assert is_money_prosperity_fact(_JOB_PREF_NOISE, "preference") is False
    assert is_money_prosperity_fact(_FRUIT_IDS_NOISE) is False
    assert is_money_prosperity_fact(_ARCHIVE_NOISE) is False
    assert is_money_prosperity_fact(_TRIAGE_DOCKET) is True
    assert is_money_prosperity_fact("Upwork send pack is ready") is True
    assert is_money_prosperity_fact(_FRUIT_HARVEST) is True
    assert is_money_prosperity_fact("Q3 revenue forecast is $40k") is True

    mgr = MemoryManager(str(tmp_path))
    noise = [
        mgr.add_entry(_JOB_PREF_NOISE, category="preference", owner="tcam"),
        mgr.add_entry(_FRUIT_IDS_NOISE, owner="tcam"),
        mgr.add_entry(_ARCHIVE_NOISE, category="event", owner="tcam"),
    ]
    keep = [
        mgr.add_entry(_TRIAGE_DOCKET, category="project", owner="tcam"),
        mgr.add_entry("Upwork send pack is ready", owner="tcam"),
        mgr.add_entry(_FRUIT_HARVEST, owner="tcam"),
    ]
    mgr.save(noise + keep)
    for entry in noise:
        assert not entry.get("pinned")
        assert "pin_origin" not in entry
    for entry in keep:
        assert entry.get("pinned") is True
        assert entry.get("pin_origin") == PIN_ORIGIN_AUTO_MONEY


def test_load_backfills_existing_money_facts_and_persists(tmp_path):
    raw = [
        {
            "id": "money-legacy",
            "text": "NPR invoice is unpaid",
            "category": "fact",
            "owner": "tcam",
            "timestamp": 111,
            "uses": 4,
            "source": "cursor",
            "session_id": "keep-me",
        },
        {
            "id": "pref-legacy",
            "text": "Prefers concise replies",
            "category": "preference",
            "owner": "tcam",
            "timestamp": 222,
            "pinned": False,
        },
        {
            "id": "already-pinned",
            "text": "Q3 retainer is $12k",
            "category": "fact",
            "owner": "tcam",
            "pinned": True,
            "timestamp": 333,
        },
        {
            "id": "user-unpinned",
            "text": "Upwork send pack is ready",
            "category": "fact",
            "owner": "tcam",
            "pinned": False,
            "pin_origin": PIN_ORIGIN_USER,
            "timestamp": 444,
        },
        "corrupt-row",
    ]
    (tmp_path / "memory.json").write_text(json.dumps(raw), encoding="utf-8")
    mgr = MemoryManager(str(tmp_path))

    disk = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in disk if isinstance(e, dict)}
    assert by_id["money-legacy"]["pinned"] is True
    assert by_id["money-legacy"]["pin_origin"] == PIN_ORIGIN_AUTO_MONEY
    assert by_id["money-legacy"]["timestamp"] == 111
    assert by_id["money-legacy"]["uses"] == 4
    assert by_id["money-legacy"]["source"] == "cursor"
    assert by_id["money-legacy"]["session_id"] == "keep-me"
    assert by_id["pref-legacy"].get("pinned") is False
    assert "pin_origin" not in by_id["pref-legacy"]
    assert by_id["already-pinned"]["pinned"] is True
    assert "pin_origin" not in by_id["already-pinned"]
    assert by_id["already-pinned"]["timestamp"] == 333
    assert by_id["user-unpinned"]["pinned"] is False
    assert by_id["user-unpinned"]["pin_origin"] == PIN_ORIGIN_USER
    assert "corrupt-row" in disk

    first = (tmp_path / "memory.json").read_text(encoding="utf-8")
    loaded = mgr.load_all()
    assert (tmp_path / "memory.json").read_text(encoding="utf-8") == first
    facts = load_pinned_memory_facts(owner="tcam", memory_manager=mgr)
    assert "NPR invoice is unpaid" in facts
    assert "Q3 retainer is $12k" in facts
    assert "Prefers concise replies" not in facts
    assert "Upwork send pack is ready" not in facts
    assert any(e["id"] == "money-legacy" and e.get("pinned") for e in loaded)


def test_load_unpins_stale_auto_money_keeps_user_and_orphan_pins(tmp_path):
    raw = [
        {
            "id": "noise-pref",
            "text": _JOB_PREF_NOISE,
            "category": "preference",
            "owner": "tcam",
            "pinned": True,
            "pin_origin": PIN_ORIGIN_AUTO_MONEY,
            "timestamp": 1783944652,
            "uses": 8,
            "source": "cursor",
        },
        {
            "id": "noise-fruit",
            "text": _FRUIT_IDS_NOISE,
            "category": "fact",
            "owner": "tcam",
            "pinned": True,
            "pin_origin": PIN_ORIGIN_AUTO_MONEY,
            "timestamp": 1783622027,
            "uses": 1,
        },
        {
            "id": "keep-docket",
            "text": _TRIAGE_DOCKET,
            "category": "project",
            "owner": "tcam",
            "pinned": True,
            "pin_origin": PIN_ORIGIN_AUTO_MONEY,
            "timestamp": 1784908841,
            "uses": 2,
        },
        {
            "id": "noise-archive",
            "text": _ARCHIVE_NOISE,
            "category": "event",
            "owner": "tcam",
            "pinned": True,
            "pin_origin": PIN_ORIGIN_AUTO_MONEY,
            "timestamp": 1785707537,
            "uses": 3,
        },
        {
            "id": "user-id",
            "text": "Call me Tylar",
            "category": "identity",
            "owner": "tcam",
            "pinned": True,
            "pin_origin": PIN_ORIGIN_USER,
            "timestamp": 5,
            "uses": 4,
        },
        {
            "id": "orphan-pin",
            "text": "Prefers concise replies",
            "category": "preference",
            "owner": "tcam",
            "pinned": True,
            "timestamp": 6,
            "uses": 0,
        },
    ]
    (tmp_path / "memory.json").write_text(json.dumps(raw), encoding="utf-8")
    mgr = MemoryManager(str(tmp_path))
    disk = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in disk}

    assert by_id["noise-pref"].get("pinned") is False
    assert "pin_origin" not in by_id["noise-pref"]
    assert by_id["noise-pref"]["timestamp"] == 1783944652
    assert by_id["noise-pref"]["uses"] == 8
    assert by_id["noise-fruit"].get("pinned") is False
    assert "pin_origin" not in by_id["noise-fruit"]
    assert by_id["noise-archive"].get("pinned") is False
    assert "pin_origin" not in by_id["noise-archive"]

    assert by_id["keep-docket"]["pinned"] is True
    assert by_id["keep-docket"]["pin_origin"] == PIN_ORIGIN_AUTO_MONEY
    assert by_id["keep-docket"]["uses"] == 2

    assert by_id["user-id"]["pinned"] is True
    assert by_id["user-id"]["pin_origin"] == PIN_ORIGIN_USER
    assert by_id["orphan-pin"]["pinned"] is True
    assert "pin_origin" not in by_id["orphan-pin"]

    facts = load_pinned_memory_facts(owner="tcam", memory_manager=mgr)
    assert _TRIAGE_DOCKET in facts
    assert "Call me Tylar" in facts
    assert "Prefers concise replies" in facts
    assert _JOB_PREF_NOISE not in facts
    assert _FRUIT_IDS_NOISE not in facts
    assert _ARCHIVE_NOISE not in facts

    first = (tmp_path / "memory.json").read_text(encoding="utf-8")
    mgr.load_all()
    assert (tmp_path / "memory.json").read_text(encoding="utf-8") == first


def test_edit_reevaluates_money_pin_without_unpinning_user_pins(tmp_path):
    mgr = MemoryManager(str(tmp_path))
    generic = mgr.add_entry("Prefers concise replies", category="preference", owner="tcam")
    auto_money = mgr.add_entry("Q3 retainer is $12k", owner="tcam")
    user_pref = mgr.add_entry("Call me Tylar", category="identity", owner="tcam")
    unknown = {
        "id": "unknown-origin",
        "text": "Vanier grant nomination packet is the live gate",
        "category": "fact",
        "owner": "tcam",
        "pinned": True,
        "timestamp": 1,
        "source": "user",
        "uses": 0,
    }
    mgr.save([generic, auto_money, user_pref, unknown])
    pin_memory_item(mgr, user_pref["id"], pinned=True, owner="tcam")

    entries = mgr.load_all()
    g = next(e for e in entries if e["id"] == generic["id"])
    g["text"] = "Vanier grant nomination packet is the live gate"
    mgr.save(entries)
    g2 = next(e for e in mgr.load_all() if e["id"] == generic["id"])
    assert g2["pinned"] is True
    assert g2["pin_origin"] == PIN_ORIGIN_AUTO_MONEY

    entries = mgr.load_all()
    m = next(e for e in entries if e["id"] == auto_money["id"])
    assert m.get("pin_origin") == PIN_ORIGIN_AUTO_MONEY
    m["text"] = "Prefers dark mode"
    mgr.save(entries)
    m2 = next(e for e in mgr.load_all() if e["id"] == auto_money["id"])
    assert not m2.get("pinned")
    assert "pin_origin" not in m2

    entries = mgr.load_all()
    u = next(e for e in entries if e["id"] == user_pref["id"])
    assert u.get("pin_origin") == PIN_ORIGIN_USER
    u["text"] = "Prefers concise replies"
    mgr.save(entries)
    u2 = next(e for e in mgr.load_all() if e["id"] == user_pref["id"])
    assert u2["pinned"] is True
    assert u2["pin_origin"] == PIN_ORIGIN_USER

    entries = mgr.load_all()
    x = next(e for e in entries if e["id"] == "unknown-origin")
    x["text"] = "Prefers concise replies"
    mgr.save(entries)
    x2 = next(e for e in mgr.load_all() if e["id"] == "unknown-origin")
    assert x2["pinned"] is True


class _Docs:
    rag_manager = None


def _chat_preface(mgr, *, use_memory=True, owner="tcam"):
    processor = ChatProcessor(memory_manager=mgr, personal_docs_manager=_Docs())
    preface, _, _ = processor.build_context_preface(
        message="what's my money move?",
        session=None,
        use_memory=use_memory,
        use_rag=False,
        owner=owner,
    )
    return preface, processor


def test_chat_preface_uses_shared_pinned_helper(tmp_path, monkeypatch):
    mgr = MemoryManager(str(tmp_path))
    money = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    other = mgr.add_entry("Prefers concise replies", category="preference", owner="tcam")
    mgr.save([money, other])

    calls = []
    real = load_pinned_memory_facts

    def wrapped(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr("src.chat_processor.load_pinned_memory_facts", wrapped)

    preface, processor = _chat_preface(mgr)
    assert calls, "chat must load pins through load_pinned_memory_facts"
    blob = "\n".join(m.get("content") or "" for m in preface)
    assert "Q3 retainer is $12k" in blob
    assert "Prefers concise replies" not in blob
    assert "saved memory: pinned user facts" in blob
    pinned_used = [m for m in processor._last_used_memories if m.get("type") == "pinned"]
    assert pinned_used and pinned_used[0]["text"] == "Q3 retainer is $12k"

    pin_memory_item(mgr, money["id"], pinned=False, owner="tcam")
    unpinned, _ = _chat_preface(mgr)
    unblob = "\n".join(m.get("content") or "" for m in unpinned)
    assert "Q3 retainer is $12k" not in unblob

    pin_memory_item(mgr, money["id"], pinned=True, owner="tcam")
    off, proc_off = _chat_preface(mgr, use_memory=False)
    offblob = "\n".join(m.get("content") or "" for m in off)
    assert "Q3 retainer is $12k" not in offblob
    assert proc_off._last_used_memories == []


def _stub_agent_prompt(monkeypatch, data_dir, memory_enabled=True):
    import sys
    import types

    import src.agent_loop as agent_loop
    import src.constants as constants

    monkeypatch.setattr(constants, "DATA_DIR", str(data_dir), raising=False)
    monkeypatch.setattr(agent_loop, "_build_base_prompt", lambda *a, **k: ("BASE PROMPT", ""))
    monkeypatch.setattr(agent_loop, "set_active_model", lambda model: None)
    monkeypatch.setattr(agent_loop, "get_builtin_overrides", lambda: {})
    agent_loop._cached_base_prompt = None
    agent_loop._cached_base_prompt_key = None
    fake_prefs = types.ModuleType("routes.prefs_routes")
    fake_prefs._load_for_user = lambda user=None: {
        "skills_enabled": False,
        "memory_enabled": memory_enabled,
    }
    monkeypatch.setitem(sys.modules, "routes.prefs_routes", fake_prefs)
    return agent_loop


def test_agent_prompt_injects_pinned_facts_not_unpinned(tmp_path, monkeypatch):
    mgr = MemoryManager(str(tmp_path))
    money = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    other = mgr.add_entry("Prefers concise replies", category="preference", owner="tcam")
    mgr.save([money, other])
    pin_memory_item(mgr, money["id"], pinned=True, owner="tcam")

    agent_loop = _stub_agent_prompt(monkeypatch, tmp_path)
    out, _ = agent_loop._build_system_prompt(
        [{"role": "user", "content": "what's my money move?"}],
        model="test-model",
        active_document=None,
        mcp_mgr=None,
        owner="tcam",
    )

    pinned_msgs = [
        m for m in out
        if "Q3 retainer is $12k" in (m.get("content") or "")
    ]
    assert pinned_msgs, "pinned money fact must land in agent prompt context"
    assert pinned_msgs[0]["role"] == "user"
    assert (pinned_msgs[0].get("metadata") or {}).get("trusted") is False
    assert "saved memory: pinned user facts" in (pinned_msgs[0].get("content") or "")
    assert all(
        "Q3 retainer is $12k" not in (m.get("content") or "")
        for m in out if m.get("role") == "system"
    )
    assert all(
        "Prefers concise replies" not in (m.get("content") or "")
        for m in out
    )

    pin_memory_item(mgr, money["id"], pinned=False, owner="tcam")
    agent_loop._cached_base_prompt = None
    agent_loop._cached_base_prompt_key = None
    unpinned_out, _ = agent_loop._build_system_prompt(
        [{"role": "user", "content": "what's my money move?"}],
        model="test-model",
        active_document=None,
        mcp_mgr=None,
        owner="tcam",
    )
    assert all(
        "Q3 retainer is $12k" not in (m.get("content") or "")
        for m in unpinned_out
    )


def test_agent_prompt_skips_pinned_facts_when_memory_disabled(tmp_path, monkeypatch):
    mgr = MemoryManager(str(tmp_path))
    money = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    mgr.save([money])
    pin_memory_item(mgr, money["id"], pinned=True, owner="tcam")

    agent_loop = _stub_agent_prompt(monkeypatch, tmp_path, memory_enabled=False)
    out, _ = agent_loop._build_system_prompt(
        [{"role": "user", "content": "hi"}],
        model="test-model",
        active_document=None,
        mcp_mgr=None,
        owner="tcam",
    )
    assert all("Q3 retainer is $12k" not in (m.get("content") or "") for m in out)


def test_agent_loop_docs_allow_pin():
    from src.agent_loop import TOOL_SECTIONS, _AGENT_RULES

    doc = TOOL_SECTIONS["manage_memory"].lower()
    assert "pin" in doc
    assert "unpin" in doc
    assert "does not delete" in doc
    assert "action=pin" in _AGENT_RULES
    assert "does not delete" in _AGENT_RULES.lower()


def test_tool_index_manage_memory_indexes_pin():
    """RAG builtin copy must mention pin so 'pin that money fact' embeds."""
    from src.tool_index import BUILTIN_TOOL_DESCRIPTIONS, ToolIndex

    desc = BUILTIN_TOOL_DESCRIPTIONS["manage_memory"]
    indexed = f"Tool: manage_memory\n{desc}".lower()
    assert "pin" in indexed
    assert "unpin" in indexed
    assert "does not delete" in indexed
    assert "money fact" in indexed
    assert "pin that money fact" in indexed
    assert "keep this in memory" in indexed
    for stale in ("list, add, edit, delete, or search persistent memories.",):
        assert stale not in desc

    pin_tools = set()
    for kws, tools in ToolIndex._KEYWORD_HINTS.items():
        if any(
            phrase in kw
            for kw in kws
            for phrase in ("pin that", "money fact", "unpin", "keep this in memory")
        ):
            pin_tools |= set(tools)
    assert "manage_memory" in pin_tools

    ti = ToolIndex.__new__(ToolIndex)
    ti.retrieve = lambda query, k=8: ["manage_notes"]
    tools = ti.get_tools_for_query("pin that money fact")
    assert "manage_memory" in tools
    tools_keep = ti.get_tools_for_query("keep this in memory")
    assert "manage_memory" in tools_keep


@pytest.mark.asyncio
async def test_mcp_manage_memory_pin_does_not_delete(tmp_path, monkeypatch):
    import mcp_servers.memory_server as ms

    mgr = MemoryManager(str(tmp_path))
    entry = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    mgr.save([entry])
    monkeypatch.setattr(ms, "_initialized", True)
    monkeypatch.setattr(ms, "_memory_manager", mgr)
    monkeypatch.setattr(ms, "_memory_vector", None)

    tools = await ms.list_tools()
    schema = tools[0].inputSchema
    enum = schema["properties"]["action"]["enum"]
    for act in ("list", "add", "edit", "delete", "search", "pin", "unpin"):
        assert act in enum
    assert "does not delete" in (tools[0].description or "").lower()

    out = await ms.call_tool("manage_memory", {"action": "pin", "memory_id": entry["id"]})
    text = out[0].text
    assert "pinned" in text.lower()
    assert "deleted" not in text.lower()
    assert "Error" not in text
    loaded = mgr.load_all()
    assert len(loaded) == 1
    assert loaded[0]["pinned"] is True
    assert loaded[0]["text"] == "Q3 retainer is $12k"

    un = await ms.call_tool("manage_memory", {"action": "unpin", "memory_id": entry["id"][:8]})
    assert "unpinned" in un[0].text.lower()
    assert "deleted" not in un[0].text.lower()
    remaining = mgr.load_all()
    assert len(remaining) == 1
    assert remaining[0]["pinned"] is False
    assert remaining[0]["text"] == "Q3 retainer is $12k"

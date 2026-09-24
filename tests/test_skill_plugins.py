"""Plugin skill discovery + shared visibility for slash catalog."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.memory.skill_plugins import discover_plugins, group_skills_by_plugin, sync_plugins_into_skills
from services.memory.skills import SkillsManager, _skill_visible_to


def test_skill_visible_to_shared_plugin():
    assert _skill_visible_to(None, "plugin:pstack", "tylarcam") is True
    assert _skill_visible_to("other", "plugin:openspec", "tylarcam") is True
    assert _skill_visible_to("tylarcam", "learned", "tylarcam") is True
    assert _skill_visible_to("other", "learned", "tylarcam") is False
    assert _skill_visible_to(None, "learned", "tylarcam") is False


def test_discover_plugins_from_cursor_root(tmp_path: Path, monkeypatch):
    cursor = tmp_path / ".cursor"
    plugin = cursor / "plugins" / "pstack"
    (plugin / ".cursor-plugin").mkdir(parents=True)
    (plugin / ".cursor-plugin" / "plugin.json").write_text(
        json.dumps({"name": "pstack", "displayName": "pstack", "version": "0.14.8", "skills": "./skills/"}),
        encoding="utf-8",
    )
    skill_dir = plugin / "skills" / "unslop"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: unslop\ndescription: Cut AI tells\n---\n\nBody.\n",
        encoding="utf-8",
    )
    openspec = cursor / "skills" / "openspec-propose"
    openspec.mkdir(parents=True)
    (openspec / "SKILL.md").write_text(
        "---\nname: openspec-propose\ndescription: Propose a change\n---\n\nBody.\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ODYSSEUS_CURSOR_ROOT", str(cursor))
    packs = discover_plugins()
    ids = {p.id for p in packs}
    assert "pstack" in ids
    assert "openspec" in ids
    pstack = next(p for p in packs if p.id == "pstack")
    assert any(s.name == "unslop" for s in pstack.skills)


def test_sync_and_load_visible_without_owner(tmp_path: Path, monkeypatch):
    cursor = tmp_path / ".cursor"
    plugin = cursor / "plugins" / "demo"
    (plugin / ".cursor-plugin").mkdir(parents=True)
    (plugin / ".cursor-plugin" / "plugin.json").write_text(
        json.dumps({"name": "demo", "skills": "./skills/"}),
        encoding="utf-8",
    )
    skill_dir = plugin / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: Say hi\n---\n\nHello.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ODYSSEUS_CURSOR_ROOT", str(cursor))

    data_dir = tmp_path / "data"
    sm = SkillsManager(str(data_dir))
    result = sync_plugins_into_skills(sm, plugin_ids=["demo"], owner=None)
    assert result["count"] >= 1

    loaded = sm.load(owner="tylarcam")
    names = {s["name"] for s in loaded}
    assert "hello" in names
    hello = next(s for s in loaded if s["name"] == "hello")
    assert hello["source"] == "plugin:demo"
    assert hello["status"] == "published"

    idx = sm.index_for(owner="tylarcam")
    assert any(s["name"] == "hello" for s in idx)

    groups = group_skills_by_plugin(loaded)
    demo = next(g for g in groups if g["id"] == "demo")
    assert any(s["name"] == "hello" and s["installed"] for s in demo["skills"])

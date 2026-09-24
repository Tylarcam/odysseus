"""Discover Cursor/Claude plugin skill packs and sync them into data/skills/.

Plugins are discovered from:
  - ``.cursor/plugins/<id>/.cursor-plugin/plugin.json`` (manifest skills root)
  - ``.cursor/skills/openspec-*`` (OpenSpec skill group without a plugin manifest)

Synced skills land at ``data/skills/<plugin>/<name>/`` with
``status: published``, ``category: <plugin>``, and ``source: plugin:<plugin>``
so the slash catalog and Settings UI can group/toggle them.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .skill_format import Skill, slugify

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = {"__pycache__", ".git", "node_modules", ".venv"}


@dataclass
class PluginSkillRef:
    name: str
    description: str = ""
    source_dir: str = ""


@dataclass
class PluginPack:
    id: str
    display_name: str
    version: str = ""
    description: str = ""
    root: str = ""
    skills: List[PluginSkillRef] = field(default_factory=list)


def repo_root() -> Path:
    """Odysseus repo root (parent of ``services/``)."""
    return Path(__file__).resolve().parents[2]


def cursor_roots(extra: Optional[Iterable[str]] = None) -> List[Path]:
    """Candidate roots that may contain ``.cursor/plugins`` / ``.cursor/skills``.

    Order matters — first hit wins when resolving a plugin id.
    """
    roots: List[Path] = []
    env = (os.environ.get("ODYSSEUS_CURSOR_ROOT") or "").strip()
    if env:
        roots.append(Path(env))
    # In-container optional mounts (see docker-compose.yml).
    roots.append(Path("/app/.cursor"))
    roots.append(repo_root() / ".cursor")
    # Host layout when data/ is the CWD-adjacent mount.
    roots.append(repo_root().parent / ".cursor")
    if extra:
        for item in extra:
            if item:
                roots.append(Path(item))
    # De-dupe while preserving order.
    out: List[Path] = []
    seen = set()
    for r in roots:
        try:
            key = str(r.resolve()) if r.exists() else str(r)
        except OSError:
            key = str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _read_skill_meta(skill_md: Path) -> tuple[str, str]:
    try:
        text = skill_md.read_text(encoding="utf-8")
        sk = Skill.from_markdown(text, path=str(skill_md))
        name = slugify(sk.name or skill_md.parent.name, fallback=skill_md.parent.name)
        return name, (sk.description or "").strip()
    except Exception as e:
        logger.debug("skill meta parse failed for %s: %s", skill_md, e)
        return slugify(skill_md.parent.name, fallback="skill"), ""


def _iter_skill_dirs(skills_root: Path) -> Iterable[Path]:
    if not skills_root.is_dir():
        return
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir() or child.name in _SKIP_DIR_NAMES:
            continue
        if (child / "SKILL.md").is_file():
            yield child


def discover_plugins() -> List[PluginPack]:
    """Return plugin packs found under any known ``.cursor`` root."""
    by_id: Dict[str, PluginPack] = {}

    for cursor_root in cursor_roots():
        plugins_dir = cursor_root / "plugins"
        if plugins_dir.is_dir():
            for plugin_dir in sorted(plugins_dir.iterdir()):
                if not plugin_dir.is_dir() or plugin_dir.name in _SKIP_DIR_NAMES:
                    continue
                manifest = plugin_dir / ".cursor-plugin" / "plugin.json"
                if not manifest.is_file():
                    continue
                try:
                    meta = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning("Failed to read plugin manifest %s: %s", manifest, e)
                    continue
                pid = slugify(str(meta.get("name") or plugin_dir.name), fallback=plugin_dir.name)
                if pid in by_id:
                    continue
                rel_skills = str(meta.get("skills") or "./skills/").strip() or "./skills/"
                skills_root = (plugin_dir / rel_skills).resolve()
                refs: List[PluginSkillRef] = []
                for skill_dir in _iter_skill_dirs(skills_root):
                    name, desc = _read_skill_meta(skill_dir / "SKILL.md")
                    refs.append(PluginSkillRef(name=name, description=desc, source_dir=str(skill_dir)))
                by_id[pid] = PluginPack(
                    id=pid,
                    display_name=str(meta.get("displayName") or meta.get("name") or pid),
                    version=str(meta.get("version") or ""),
                    description=str(meta.get("description") or ""),
                    root=str(plugin_dir),
                    skills=refs,
                )

        # OpenSpec (and similar) live as loose skills under .cursor/skills/.
        skills_dir = cursor_root / "skills"
        if skills_dir.is_dir():
            openspec_refs: List[PluginSkillRef] = []
            for skill_dir in _iter_skill_dirs(skills_dir):
                if not skill_dir.name.startswith("openspec-"):
                    continue
                name, desc = _read_skill_meta(skill_dir / "SKILL.md")
                openspec_refs.append(
                    PluginSkillRef(name=name, description=desc, source_dir=str(skill_dir))
                )
            if openspec_refs and "openspec" not in by_id:
                by_id["openspec"] = PluginPack(
                    id="openspec",
                    display_name="OpenSpec",
                    description="OpenSpec change workflow skills",
                    root=str(skills_dir),
                    skills=openspec_refs,
                )

    return sorted(by_id.values(), key=lambda p: p.id)


def _copy_skill_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _ignore(_dir: str, names: List[str]) -> set:
        return {n for n in names if n in _SKIP_DIR_NAMES or n.endswith(".pyc")}

    shutil.copytree(src, dest, ignore=_ignore)


def _patch_frontmatter_raw(text: str, updates: Dict[str, object]) -> str:
    """Merge keys into YAML frontmatter without rewriting the markdown body.

    Round-tripping through ``Skill.to_markdown()`` drops unknown ``##`` headings
    (they become section delimiters with no key). Plugin skills rely on those
    headings, so we only touch the frontmatter block.
    """
    if not text.startswith("---"):
        fm_lines = [f"{k}: {_emit_fm_scalar(v)}" for k, v in updates.items() if v is not None and v != ""]
        return "---\n" + "\n".join(fm_lines) + "\n---\n\n" + text.lstrip("\n")

    end = text.find("\n---", 3)
    if end < 0:
        fm_lines = [f"{k}: {_emit_fm_scalar(v)}" for k, v in updates.items() if v is not None and v != ""]
        return "---\n" + "\n".join(fm_lines) + "\n---\n\n" + text

    fm_text = text[3:end].lstrip("\n")
    body = text[end + 4:].lstrip("\n")
    lines = fm_text.splitlines()
    keys_done = set()
    out_lines: List[str] = []
    for line in lines:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            out_lines.append(line)
            continue
        key = m.group(1)
        if key in updates:
            out_lines.append(f"{key}: {_emit_fm_scalar(updates[key])}")
            keys_done.add(key)
        else:
            out_lines.append(line)
    for key, val in updates.items():
        if key in keys_done or val is None or val == "":
            continue
        out_lines.append(f"{key}: {_emit_fm_scalar(val)}")
    return "---\n" + "\n".join(out_lines).rstrip() + "\n---\n\n" + body


def _emit_fm_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if any(c in s for c in (":", "#", "{", "}", "[", "]", ",", "\n", '"', "'")) or s != s.strip():
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _publish_frontmatter(skill_md: Path, *, plugin_id: str, skill_name: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    patched = _patch_frontmatter_raw(
        text,
        {
            "name": skill_name,
            "category": plugin_id,
            "status": "published",
            "source": f"plugin:{plugin_id}",
        },
    )
    from core.atomic_io import atomic_write_text

    atomic_write_text(str(skill_md), patched)


def sync_plugins_into_skills(
    skills_manager,
    *,
    plugin_ids: Optional[List[str]] = None,
    owner: Optional[str] = None,
) -> Dict:
    """Copy discovered plugin skills into ``data/skills/<plugin>/``.

    Returns a summary dict suitable for an API response.
    """
    wanted = {slugify(p, fallback=p) for p in (plugin_ids or []) if p} or None
    packs = discover_plugins()
    if wanted is not None:
        packs = [p for p in packs if p.id in wanted]

    added = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    synced: List[Dict] = []

    for pack in packs:
        for ref in pack.skills:
            src = Path(ref.source_dir)
            if not src.is_dir() or not (src / "SKILL.md").is_file():
                skipped += 1
                continue
            dest = Path(skills_manager._skill_dir(pack.id, ref.name))
            existed = dest.is_dir() and (dest / "SKILL.md").is_file()
            try:
                _copy_skill_tree(src, dest)
                _publish_frontmatter(dest / "SKILL.md", plugin_id=pack.id, skill_name=ref.name)
                if owner:
                    sk = skills_manager._read_skill(str(dest / "SKILL.md"))
                    if sk and (sk.owner or "") != owner:
                        sk.owner = owner
                        skills_manager._write_skill(sk)
                if existed:
                    updated += 1
                else:
                    added += 1
                synced.append({"plugin": pack.id, "name": ref.name, "updated": existed})
            except Exception as e:
                logger.exception("Failed syncing skill %s/%s", pack.id, ref.name)
                errors.append(f"{pack.id}/{ref.name}: {e}")

    return {
        "ok": not errors,
        "plugins": [p.id for p in packs],
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "synced": synced,
        "count": added + updated,
    }


def group_skills_by_plugin(skills: List[Dict], packs: Optional[List[PluginPack]] = None) -> List[Dict]:
    """Build Settings-ready plugin groups from installed skills + discovery.

    Grouping keys (first match wins):
      1. ``source`` starting with ``plugin:``
      2. ``category`` matching a discovered plugin id
      3. ``category`` starting with ``openspec`` → openspec
      4. else ``odysseus`` (learned / imported app skills)
    """
    packs = packs if packs is not None else discover_plugins()
    pack_meta = {p.id: p for p in packs}
    known_ids = set(pack_meta)

    groups: Dict[str, Dict] = {}

    def _ensure(pid: str) -> Dict:
        if pid not in groups:
            meta = pack_meta.get(pid)
            groups[pid] = {
                "id": pid,
                "display_name": (meta.display_name if meta else ("Odysseus" if pid == "odysseus" else pid)),
                "version": (meta.version if meta else ""),
                "description": (meta.description if meta else ""),
                "skills": [],
            }
        return groups[pid]

    # Ensure discovered packs appear even before sync.
    for p in packs:
        g = _ensure(p.id)
        existing = {s["name"] for s in g["skills"]}
        for ref in p.skills:
            if ref.name in existing:
                continue
            g["skills"].append({
                "name": ref.name,
                "description": ref.description,
                "installed": False,
                "enabled": True,
                "category": p.id,
                "source": f"plugin:{p.id}",
            })

    for sk in skills or []:
        if not isinstance(sk, dict):
            continue
        name = (sk.get("name") or "").strip()
        if not name:
            continue
        source = str(sk.get("source") or "")
        category = str(sk.get("category") or "general")
        if source.startswith("plugin:"):
            pid = slugify(source.split(":", 1)[1], fallback="plugin")
        elif category in known_ids:
            pid = category
        elif category.startswith("openspec") or name.startswith("openspec-"):
            pid = "openspec"
        else:
            pid = "odysseus"
        g = _ensure(pid)
        row = {
            "name": name,
            "description": sk.get("description") or sk.get("title") or "",
            "installed": True,
            "enabled": True,  # caller overlays disabled_skills
            "category": category,
            "source": source,
            "status": sk.get("status") or "published",
        }
        # Replace discovery stub if present.
        replaced = False
        for i, existing in enumerate(g["skills"]):
            if existing.get("name") == name:
                g["skills"][i] = row
                replaced = True
                break
        if not replaced:
            g["skills"].append(row)

    out = list(groups.values())
    for g in out:
        g["skills"].sort(key=lambda s: s.get("name") or "")
        g["skill_count"] = len(g["skills"])
    out.sort(key=lambda g: (0 if g["id"] == "odysseus" else 1, g["display_name"].lower()))
    return out

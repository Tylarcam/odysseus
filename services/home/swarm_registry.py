"""Explicit Mycelia swarm-task registry.

Swarm membership is metadata — never inferred from an ID prefix or a title
substring. Seeded from the historical ``swarm-*`` tasks/docs (see
``scripts/seed_swarm.py``); new swarm agents must be added here to appear in
MYCELIA ``agent_activity`` / ``mycelia_commands``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SwarmTaskSpec:
    """One registered swarm scheduled-task."""

    task_id: str
    display_name: str
    role: str = ""
    command_id: Optional[str] = None
    command_label: Optional[str] = None
    is_coo: bool = False
    command_order: int = 100


@dataclass(frozen=True)
class SwarmDocSpec:
    """One registered swarm document reference.

    Docs are resolved against live document rows by title keys (all must appear
    case-insensitively). Keys live here — not inline in cmd_center — so
    coincidence matching stays scoped to registered docs only.

    When ``pinned_doc_id`` is set it wins over title matching (canonical board).
    """

    key: str
    display_name: str
    title_keys: Tuple[str, ...]
    command_id: str
    command_label: str
    pinned_doc_id: Optional[str] = None


# Migrated from seed_swarm.TASKS + the hardcoded MYCELIA doc lookups that used
# to live in cmd_center.py (_find_doc("fruit","ledger") / doctrine / substrate).
SWARM_TASKS: Tuple[SwarmTaskSpec, ...] = (
    SwarmTaskSpec(
        "swarm-t-sporangium-am",
        "Morning plan & routing",
        role="coo",
        command_id="myc_coo",
        command_label="Run COO Plan",
        is_coo=True,
        command_order=10,
    ),
    SwarmTaskSpec("swarm-t-sporangium-pm", "Afternoon re-plan", role="coo"),
    SwarmTaskSpec("swarm-t-spore", "Decompose inbound", role="spore"),
    SwarmTaskSpec(
        "swarm-t-forager",
        "Pipeline scan & stage",
        role="forager",
        command_id="myc_forager",
        command_label="Dispatch Forager",
        command_order=20,
    ),
    SwarmTaskSpec(
        "swarm-t-rhizo",
        "Research day's priorities",
        role="rhizo",
        command_id="myc_rhizo",
        command_label="Send to Research",
        command_order=30,
    ),
    SwarmTaskSpec(
        "swarm-t-scout",
        "Inbox triage",
        role="scout",
        command_id="myc_scout",
        command_label="Dispatch Scout",
        command_order=40,
    ),
    SwarmTaskSpec("swarm-t-scribe", "Draft outstanding artifacts", role="scribe"),
    SwarmTaskSpec("swarm-t-sentinel", "Verify staged drafts", role="sentinel"),
    SwarmTaskSpec("swarm-t-gatekeeper", "Assemble approval packages", role="gatekeeper"),
    SwarmTaskSpec("swarm-t-herald", "Daily brief + Fruit Ledger", role="herald"),
    SwarmTaskSpec("swarm-t-keeper", "Memory consolidation + spores", role="keeper"),
    SwarmTaskSpec("swarm-t-loam", "Substrate tidy", role="loam"),
    SwarmTaskSpec("swarm-t-culler", "Health watch", role="culler"),
)

SWARM_DOCS: Tuple[SwarmDocSpec, ...] = (
    SwarmDocSpec(
        key="ledger",
        display_name="Fruit Ledger",
        title_keys=("fruit", "ledger"),
        command_id="myc_fruit",
        command_label="Fruit Ledger",
    ),
    SwarmDocSpec(
        key="board",
        display_name="Blackboard",
        title_keys=("blackboard",),
        pinned_doc_id="30abbc6f-756d-4a00-a9f6-3ef69e806f34",
        command_id="myc_board",
        command_label="Blackboard",
    ),
    SwarmDocSpec(
        key="doctrine",
        display_name="Swarm Doctrine",
        title_keys=("swarm", "doctrine"),
        command_id="myc_doc",
        command_label="Swarm Doctrine",
    ),
)

_SWARM_TASK_BY_ID: Dict[str, SwarmTaskSpec] = {t.task_id: t for t in SWARM_TASKS}
_SWARM_TASK_IDS = frozenset(_SWARM_TASK_BY_ID)


def is_swarm_task_id(task_id: Any) -> bool:
    """True only when ``task_id`` is explicitly registered."""
    return str(task_id or "") in _SWARM_TASK_IDS


def swarm_task_ids() -> frozenset:
    return _SWARM_TASK_IDS


def get_swarm_task(task_id: Any) -> Optional[SwarmTaskSpec]:
    return _SWARM_TASK_BY_ID.get(str(task_id or ""))


def coo_task_spec() -> Optional[SwarmTaskSpec]:
    for spec in SWARM_TASKS:
        if spec.is_coo:
            return spec
    return None


def dispatchable_task_specs() -> Tuple[SwarmTaskSpec, ...]:
    """Specs that expose a Mycelia command-deck button (when the task exists)."""
    return tuple(
        sorted(
            (t for t in SWARM_TASKS if t.command_id and t.command_label),
            key=lambda t: (t.command_order, t.task_id),
        )
    )


def filter_swarm_tasks(tasks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return live task rows whose ids are in the registry (order preserved)."""
    return [t for t in tasks if is_swarm_task_id(t.get("id"))]


def _doc_title(doc: Dict[str, Any]) -> str:
    return str(doc.get("title") or doc.get("name") or "").strip().lower()


def resolve_swarm_docs(documents: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map registry doc key → first matching live document row."""
    by_id = {str(d.get("id") or ""): d for d in documents}
    found: Dict[str, Dict[str, Any]] = {}
    for spec in SWARM_DOCS:
        if spec.pinned_doc_id and spec.pinned_doc_id in by_id:
            found[spec.key] = by_id[spec.pinned_doc_id]
            continue
        for doc in documents:
            title = _doc_title(doc)
            if title and all(k in title for k in spec.title_keys):
                found[spec.key] = doc
                break
    return found

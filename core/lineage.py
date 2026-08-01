"""Lineage backbone — fail-soft edge writes + batched reads.

See openspec/changes/cmd-center-active-systems (cmd-center-lineage / D1).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence, Union

from core.database import LineageEdge, SessionLocal, utcnow_naive

logger = logging.getLogger(__name__)

KindId = tuple[str, str]
KindIdLike = Union[KindId, Sequence[str]]


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def record_lineage_edge(
    *,
    source_kind: str,
    source_id: str,
    target_kind: str,
    target_id: str,
    relation: str,
) -> bool:
    """Persist one lineage edge. Never raises into the caller's primary action.

    Returns True on success, False on failure (logged).
    """
    sk = (source_kind or "").strip()
    sid = (source_id or "").strip()
    tk = (target_kind or "").strip()
    tid = (target_id or "").strip()
    rel = (relation or "").strip()
    if not (sk and sid and tk and tid and rel):
        logger.warning(
            "lineage: skip incomplete edge source=%s:%s target=%s:%s relation=%r",
            source_kind,
            source_id,
            target_kind,
            target_id,
            relation,
        )
        return False

    db = None
    try:
        db = SessionLocal()
        db.add(
            LineageEdge(
                id=str(uuid.uuid4()),
                source_kind=sk,
                source_id=sid,
                target_kind=tk,
                target_id=tid,
                relation=rel,
                created_at=utcnow_naive(),
            )
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "lineage: failed to record edge %s:%s -[%s]-> %s:%s: %s",
            sk,
            sid,
            rel,
            tk,
            tid,
            exc,
        )
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        return False
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _normalize_pair(pair: KindIdLike) -> Optional[KindId]:
    if pair is None:
        return None
    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
        kind = str(pair[0] or "").strip()
        oid = str(pair[1] or "").strip()
        if kind and oid:
            return (kind, oid)
    return None


def count_lineage_edges(
    *,
    relation: str,
    since: Optional[datetime] = None,
) -> int:
    """Count edges matching ``relation``, optionally since a timestamp.

    Fail-soft: returns 0 on any DB error. ``since`` is compared against
    ``created_at`` (naive UTC, same as writers).
    """
    rel = (relation or "").strip()
    if not rel:
        return 0

    db = None
    try:
        db = SessionLocal()
        q = db.query(LineageEdge).filter(LineageEdge.relation == rel)
        if since is not None:
            q = q.filter(LineageEdge.created_at >= _as_naive_utc(since))
        return int(q.count())
    except Exception as exc:
        logger.warning("lineage: count failed relation=%r: %s", rel, exc)
        return 0
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def lineage_for(
    kind_id_pairs: Iterable[KindIdLike],
) -> dict[KindId, list[dict[str, Any]]]:
    """Batched 1-hop lineage lookup for a set of (kind, id) pairs.

    For each requested object, returns related neighbors as
    ``[{kind, id, relation}, ...]`` — the other endpoint of any edge where
    the object appears as source or target. Empty list when no edges exist
    (including pre-capability historical objects).
    """
    pairs: list[KindId] = []
    seen: set[KindId] = set()
    for raw in kind_id_pairs or []:
        pair = _normalize_pair(raw)
        if pair and pair not in seen:
            seen.add(pair)
            pairs.append(pair)

    out: dict[KindId, list[dict[str, Any]]] = {p: [] for p in pairs}
    if not pairs:
        return out

    kinds = {p[0] for p in pairs}
    ids = {p[1] for p in pairs}
    db = None
    try:
        db = SessionLocal()
        rows = (
            db.query(LineageEdge)
            .filter(
                (
                    (LineageEdge.source_kind.in_(kinds) & LineageEdge.source_id.in_(ids))
                    | (LineageEdge.target_kind.in_(kinds) & LineageEdge.target_id.in_(ids))
                )
            )
            .all()
        )
        for edge in rows:
            src = (edge.source_kind, edge.source_id)
            tgt = (edge.target_kind, edge.target_id)
            if src in out:
                out[src].append(
                    {"kind": edge.target_kind, "id": edge.target_id, "relation": edge.relation}
                )
            if tgt in out:
                out[tgt].append(
                    {"kind": edge.source_kind, "id": edge.source_id, "relation": edge.relation}
                )
    except Exception as exc:
        logger.warning("lineage: batched read failed: %s", exc)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    return out

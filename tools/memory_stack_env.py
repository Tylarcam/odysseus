"""Load archivist.ai memory_stack.env for all stack components."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV_PATH = _REPO_ROOT / "memory_stack.env"


def repo_root() -> Path:
    return _REPO_ROOT


def load_memory_stack_env(env_path: Path | None = None) -> Dict[str, str]:
    """Parse memory_stack.env into a dict and set os.environ for each key."""
    path = env_path or _DEFAULT_ENV_PATH
    values: Dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
        os.environ[key] = value

    return values


def resolve_path(key: str, default: str = "", env: Dict[str, str] | None = None) -> Path:
    """Resolve a config path relative to repo root when not absolute."""
    cfg = env if env is not None else load_memory_stack_env()
    raw = cfg.get(key) or os.environ.get(key) or default
    path = Path(raw)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return path

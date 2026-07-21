"""Launch Clicky overlay stack (worker adapter + Windows WPF app)."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from core.platform_compat import IS_WINDOWS, detached_popen_kwargs
from tools.memory_stack_env import load_memory_stack_env, repo_root, resolve_path

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_PORT = "40001"
DEFAULT_WORKER_PORT = "40002"


def _worker_port(env: Dict[str, str]) -> int:
    raw = env.get("CLICKY_WORKER_PORT") or DEFAULT_WORKER_PORT
    try:
        return int(raw)
    except ValueError:
        return int(DEFAULT_WORKER_PORT)


def _memory_port(env: Dict[str, str]) -> int:
    raw = env.get("UNIFIED_MEMORY_API_PORT") or DEFAULT_MEMORY_PORT
    try:
        return int(raw)
    except ValueError:
        return int(DEFAULT_MEMORY_PORT)


def _python_exe(root: Path) -> str:
    venv = root / "venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return str(venv)
    return os.environ.get("PYTHON", "python")


def _clicky_project_dir(env: Dict[str, str]) -> Path:
    return resolve_path("CLICKY_WINDOWS_DIR", "clicky-windows", env) / "clicky-windows"


def _fetch_json(url: str, *, method: str = "GET", json_body: Optional[dict] = None, timeout: float = 3.0) -> Optional[dict]:
    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "POST":
                response = client.post(url, json=json_body or {})
            else:
                response = client.get(url)
            if response.status_code >= 400:
                return None
            return response.json()
    except Exception:
        return None


def _worker_has_mic_routes(port: int) -> bool:
    claim = _fetch_json(
        f"http://127.0.0.1:{port}/mic/claim",
        method="POST",
        json_body={"holder": "clicky", "mode": "ptt", "ttl_sec": 5},
    )
    if not claim:
        return False
    if claim.get("ok") and claim.get("token"):
        _fetch_json(
            f"http://127.0.0.1:{port}/mic/release",
            method="POST",
            json_body={"holder": "clicky", "token": claim["token"]},
        )
        return True
    # 409 would mean route exists but mic busy — still counts as ready.
    return False


def _worker_has_endpoint_chat(port: int) -> bool:
    health = _fetch_json(f"http://127.0.0.1:{port}/health")
    return bool(health and health.get("chat_mode") == "endpoint")


def worker_ready(port: int) -> bool:
    return _worker_has_mic_routes(port) and _worker_has_endpoint_chat(port)


def worker_health(port: int) -> Dict[str, Any]:
    health = _fetch_json(f"http://127.0.0.1:{port}/health") or {}
    return {
        "listening": bool(health),
        "ready": worker_ready(port),
        "health": health,
    }


def memory_api_health(port: int) -> bool:
    health = _fetch_json(f"http://127.0.0.1:{port}/health")
    return bool(health and health.get("status") == "ok")


def _stop_listener_on_port(port: int) -> None:
    if not IS_WINDOWS:
        return
    ps = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _spawn_detached(argv: list, *, cwd: Path, env: Dict[str, str]) -> int:
    proc_env = os.environ.copy()
    proc_env.update(env)
    proc_env["PYTHONPATH"] = str(repo_root())
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=proc_env,
        **detached_popen_kwargs(),
    )
    return proc.pid


def _wait_for_worker(port: int, *, attempts: int = 10, delay_sec: float = 1.0) -> bool:
    for _ in range(attempts):
        if worker_ready(port):
            return True
        time.sleep(delay_sec)
    return False


def ensure_worker_running(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Start or restart the Clicky worker adapter on localhost."""
    cfg = env if env is not None else load_memory_stack_env()
    port = _worker_port(cfg)
    root = repo_root()

    if worker_ready(port):
        return {"started": False, "restarted": False, "port": port, "ready": True}

    if _fetch_json(f"http://127.0.0.1:{port}/health"):
        _stop_listener_on_port(port)
        time.sleep(1)

    pid = _spawn_detached([_python_exe(root), "-m", "tools.clicky_worker_api"], cwd=root, env=cfg)
    ready = _wait_for_worker(port)
    return {
        "started": True,
        "restarted": True,
        "port": port,
        "pid": pid,
        "ready": ready,
    }


def _find_clicky_exe(project_dir: Path) -> Optional[Path]:
    matches = sorted(project_dir.glob("bin/**/ClickyWindows.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _build_clicky_app(project_dir: Path) -> tuple[bool, str]:
    result = subprocess.run(
        ["dotnet", "build"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"dotnet build failed ({result.returncode})"
    return True, ""


def launch_clicky_app(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Build and launch the Clicky WPF overlay detached."""
    cfg = env if env is not None else load_memory_stack_env()
    project_dir = _clicky_project_dir(cfg)
    csproj = project_dir / "ClickyWindows.csproj"
    if not csproj.is_file():
        return {
            "ok": False,
            "error": f"ClickyWindows.csproj not found at {project_dir}. Set CLICKY_WINDOWS_DIR in memory_stack.env.",
        }

    ok, err = _build_clicky_app(project_dir)
    if not ok:
        return {"ok": False, "error": err}

    exe = _find_clicky_exe(project_dir)
    if exe and exe.is_file():
        pid = _spawn_detached([str(exe)], cwd=exe.parent, env=cfg)
        return {"ok": True, "pid": pid, "exe": str(exe)}

    pid = _spawn_detached(["dotnet", "run", "--no-build"], cwd=project_dir, env=cfg)
    return {"ok": True, "pid": pid, "exe": None}


def get_clicky_status() -> Dict[str, Any]:
    cfg = load_memory_stack_env()
    worker_port = _worker_port(cfg)
    memory_port = _memory_port(cfg)
    worker = worker_health(worker_port)
    return {
        "platform": "windows" if IS_WINDOWS else os.name,
        "supported": IS_WINDOWS,
        "memory_api": {
            "port": memory_port,
            "healthy": memory_api_health(memory_port),
        },
        "worker": {
            "port": worker_port,
            **worker,
        },
        "clicky_project": str(_clicky_project_dir(cfg)),
    }


def start_clicky(*, launch_app: bool = True) -> Dict[str, Any]:
    """Ensure worker is healthy and optionally launch the WPF overlay."""
    if not IS_WINDOWS:
        return {
            "ok": False,
            "error": "Clicky overlay launch is only supported on native Windows (not Docker/Linux).",
        }

    cfg = load_memory_stack_env()
    memory_port = _memory_port(cfg)
    worker_result = ensure_worker_running(cfg)
    if not worker_result.get("ready"):
        return {
            "ok": False,
            "error": (
                f"Clicky worker did not become healthy on port {worker_result.get('port')}. "
                "Try running: python -m tools.clicky_worker_api"
            ),
            "worker": worker_result,
            "memory_api_healthy": memory_api_health(memory_port),
        }

    payload: Dict[str, Any] = {
        "ok": True,
        "message": "Clicky worker ready. Hold Ctrl+Alt to talk once the tray icon appears.",
        "worker": worker_result,
        "memory_api_healthy": memory_api_health(memory_port),
        "worker_health": worker_health(_worker_port(cfg)).get("health") or {},
    }

    if not launch_app:
        payload["message"] = "Clicky worker ready on localhost."
        return payload

    app_result = launch_clicky_app(cfg)
    payload["app"] = app_result
    if not app_result.get("ok"):
        payload["ok"] = False
        payload["error"] = app_result.get("error") or "Failed to launch Clicky app"
        payload["message"] = payload["error"]
        return payload

    payload["message"] = "Clicky overlay launched. Hold Ctrl+Alt to talk."
    return payload

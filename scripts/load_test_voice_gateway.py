#!/usr/bin/env python3
"""Load and soak test Odysseus voice gateway endpoints.

Exercises:
  GET  /api/voice/stats
  GET  /api/voice/slo
  POST /api/voice/telemetry  (batched turn events)
  POST /api/voice/connect    (SDP negotiation — optional, needs OpenAI key)

Examples:
  python scripts/load_test_voice_gateway.py --dry-run
  python scripts/load_test_voice_gateway.py --bearer ody_... --telemetry-batches 50
  python scripts/load_test_voice_gateway.py --soak-minutes 30 --interval-sec 60 --bearer ody_...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "voice"

MINIMAL_SDP_OFFER = """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=msid-semantic: WMS
m=audio 9 UDP/TLS/RTP/SAVPF 111
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:load
a=ice-pwd:loadtestloadtestloadtestload
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=mid:0
a=sendrecv
a=rtcp-mux
a=rtpmap:111 opus/48000/2
"""


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    weight = rank - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def _auth_headers(cookie: Optional[str], bearer: Optional[str]) -> dict:
    headers: dict = {}
    if cookie:
        headers["Cookie"] = cookie
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def _load_golden_events(name: str = "golden_realtime_turn.json") -> List[dict]:
    path = FIXTURES / name
    if not path.is_file():
        return [
            {"event": "turn.start", "elapsedMs": 0},
            {"event": "mic.start", "elapsedMs": 50},
            {"event": "first_audio_out", "elapsedMs": 900},
            {"event": "response.done", "elapsedMs": 4000},
        ]
    spec = json.loads(path.read_text(encoding="utf-8"))
    return list(spec.get("sample_events", []))


def _telemetry_payload(turn_index: int) -> dict:
    turn_id = f"load-{turn_index}-{uuid.uuid4().hex[:8]}"
    events = [dict(ev, turnId=turn_id) for ev in _load_golden_events()]
    return {"turns": [{"turnId": turn_id, "events": events}]}


async def _timed_request(coro) -> Tuple[int, float, Optional[dict]]:
    t0 = time.perf_counter()
    try:
        resp = await coro
        elapsed = time.perf_counter() - t0
        body = None
        try:
            body = resp.json()
        except Exception:
            body = {"status": resp.status_code, "text": resp.text[:200]}
        return resp.status_code, elapsed, body
    except httpx.HTTPError as exc:
        return 0, time.perf_counter() - t0, {"error": str(exc)}


async def _one_connect(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    sem: asyncio.Semaphore,
) -> Tuple[int, float]:
    async with sem:
        connect_headers = {**headers, "Content-Type": "application/sdp"}
        t0 = time.perf_counter()
        try:
            resp = await client.post(url, content=MINIMAL_SDP_OFFER, headers=connect_headers)
            status = resp.status_code
        except httpx.HTTPError:
            status = 0
        return status, time.perf_counter() - t0


async def run_connect_load(
    base_url: str,
    requests: int,
    concurrency: int,
    headers: dict,
    timeout: float,
) -> dict:
    url = f"{base_url.rstrip('/')}/api/voice/connect"
    sem = asyncio.Semaphore(max(1, concurrency))
    latencies: List[float] = []
    status_counts: dict[int, int] = {}

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        tasks = [_one_connect(client, url, headers, sem) for _ in range(requests)]
        results = await asyncio.gather(*tasks)

    for status, elapsed in results:
        latencies.append(elapsed)
        status_counts[status] = status_counts.get(status, 0) + 1

    ok_latencies = [e for (s, e) in results if s == 200]
    return {
        "endpoint": "connect",
        "requests": requests,
        "concurrency": concurrency,
        "status_counts": status_counts,
        "latency_all_s": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "max": max(latencies) if latencies else None,
        },
        "latency_200_s": {
            "count": len(ok_latencies),
            "p50": _percentile(ok_latencies, 50),
            "p95": _percentile(ok_latencies, 95),
        },
    }


async def run_telemetry_load(
    base_url: str,
    batches: int,
    concurrency: int,
    headers: dict,
    timeout: float,
) -> dict:
    url = f"{base_url.rstrip('/')}/api/voice/telemetry"
    sem = asyncio.Semaphore(max(1, concurrency))
    latencies: List[float] = []
    status_counts: dict[int, int] = {}
    recorded_total = 0
    last_slo: Optional[dict] = None

    async def _post_batch(i: int) -> Tuple[int, float, Optional[dict]]:
        async with sem:
            payload = _telemetry_payload(i)
            return await _timed_request(
                client.post(url, json=payload, headers={**headers, "Content-Type": "application/json"})
            )

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        tasks = [_post_batch(i) for i in range(batches)]
        results = await asyncio.gather(*tasks)

    for status, elapsed, body in results:
        latencies.append(elapsed)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == 200 and isinstance(body, dict):
            recorded_total += int(body.get("recorded", 0))
            last_slo = body.get("slo")

    return {
        "endpoint": "telemetry",
        "batches": batches,
        "concurrency": concurrency,
        "status_counts": status_counts,
        "recorded_turns": recorded_total,
        "last_slo": last_slo,
        "latency_s": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "max": max(latencies) if latencies else None,
        },
    }


async def probe_public_endpoints(base_url: str, timeout: float, headers: Optional[dict] = None) -> dict:
    base = base_url.rstrip("/")
    out: Dict[str, Any] = {}
    req_headers = headers or {}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for path in ("/api/voice/stats", "/api/voice/slo"):
            status, elapsed, body = await _timed_request(
                client.get(f"{base}{path}", headers=req_headers)
            )
            out[path] = {"status": status, "latency_s": round(elapsed, 4), "body": body}
    return out


async def run_soak(
    base_url: str,
    minutes: float,
    interval_sec: float,
    headers: dict,
    timeout: float,
    connect_each_cycle: bool,
) -> dict:
    """Periodic telemetry + SLO probe for sustained gateway health."""
    deadline = time.monotonic() + minutes * 60
    cycle = 0
    cycles: List[dict] = []
    errors: List[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        while time.monotonic() < deadline:
            cycle += 1
            t0 = time.monotonic()
            cycle_report: Dict[str, Any] = {"cycle": cycle}

            status, elapsed, slo_body = await _timed_request(
                client.get(f"{base_url.rstrip('/')}/api/voice/slo", headers=headers)
            )
            cycle_report["slo"] = {"status": status, "latency_s": round(elapsed, 4), "body": slo_body}
            if status != 200:
                errors.append(f"cycle {cycle}: slo status {status}")

            status, elapsed, _ = await _timed_request(
                client.post(
                    f"{base_url.rstrip('/')}/api/voice/telemetry",
                    json=_telemetry_payload(cycle),
                    headers={**headers, "Content-Type": "application/json"},
                )
            )
            cycle_report["telemetry"] = {"status": status, "latency_s": round(elapsed, 4)}
            if status not in (200, 429):
                errors.append(f"cycle {cycle}: telemetry status {status}")
            elif status == 429:
                cycle_report["telemetry"]["rate_limited"] = True

            if connect_each_cycle:
                connect_headers = {**headers, "Content-Type": "application/sdp"}
                status, elapsed, _ = await _timed_request(
                    client.post(
                        f"{base_url.rstrip('/')}/api/voice/connect",
                        content=MINIMAL_SDP_OFFER,
                        headers=connect_headers,
                    )
                )
                cycle_report["connect"] = {"status": status, "latency_s": round(elapsed, 4)}
                if status not in (200, 429, 503):
                    errors.append(f"cycle {cycle}: connect status {status}")

            cycle_report["duration_s"] = round(time.monotonic() - t0, 3)
            cycles.append(cycle_report)
            print(
                f"  soak cycle {cycle}: slo={cycle_report['slo']['status']} "
                f"telemetry={cycle_report['telemetry']['status']}"
            )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval_sec, remaining))

    return {
        "soak_minutes": minutes,
        "interval_sec": interval_sec,
        "cycles": len(cycles),
        "errors": errors,
        "healthy": len(errors) == 0,
        "last_cycle": cycles[-1] if cycles else None,
    }


def _print_summary(label: str, data: dict) -> None:
    print(f"\n{label}")
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k2, v2 in value.items():
                print(f"    {k2}: {v2}")
        else:
            print(f"  {key}: {value}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Load/soak test Odysseus voice gateway")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Odysseus origin")
    parser.add_argument("--cookie", help="Session cookie header value")
    parser.add_argument("--bearer", help="Bearer token (ody_…)")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit")

    parser.add_argument("--connect-requests", type=int, default=0, help="Concurrent /connect calls (0=skip)")
    parser.add_argument("--connect-concurrency", type=int, default=3)
    parser.add_argument("--telemetry-batches", type=int, default=20, help="Concurrent telemetry POSTs")
    parser.add_argument("--telemetry-concurrency", type=int, default=5)

    parser.add_argument("--soak-minutes", type=float, default=0, help="Run soak loop for N minutes")
    parser.add_argument("--interval-sec", type=float, default=60.0, help="Soak cycle interval")
    parser.add_argument(
        "--soak-connect",
        action="store_true",
        help="Include /connect each soak cycle (needs OpenAI key; may hit rate limits)",
    )
    parser.add_argument("--skip-telemetry-load", action="store_true")
    parser.add_argument("--skip-probe", action="store_true")

    args = parser.parse_args(argv)

    if args.dry_run:
        print(
            f"base={args.base_url} connect={args.connect_requests} "
            f"telemetry={args.telemetry_batches} soak={args.soak_minutes}m"
        )
        return 0

    headers = _auth_headers(args.cookie, args.bearer)
    if not args.cookie and not args.bearer:
        print("warning: no --cookie or --bearer; telemetry/connect expect 401", file=sys.stderr)

    async def _run() -> int:
        exit_code = 0

        if not args.skip_probe:
            probe = await probe_public_endpoints(args.base_url, args.timeout, headers)
            _print_summary("Public probes (/stats, /slo)", probe)

        if not args.skip_telemetry_load and args.telemetry_batches > 0:
            tel = await run_telemetry_load(
                args.base_url,
                args.telemetry_batches,
                args.telemetry_concurrency,
                headers,
                args.timeout,
            )
            _print_summary("Telemetry load", tel)
            if tel["status_counts"].get(200, 0) == 0 and headers:
                exit_code = 1

        if args.connect_requests > 0:
            conn = await run_connect_load(
                args.base_url,
                args.connect_requests,
                args.connect_concurrency,
                headers,
                args.timeout,
            )
            _print_summary("Connect load", conn)

        if args.soak_minutes > 0:
            print(f"\nSoak test ({args.soak_minutes} min @ {args.interval_sec}s interval)")
            soak = await run_soak(
                args.base_url,
                args.soak_minutes,
                args.interval_sec,
                headers,
                args.timeout,
                args.soak_connect,
            )
            _print_summary("Soak result", soak)
            if not soak["healthy"]:
                exit_code = 1

        return exit_code

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())

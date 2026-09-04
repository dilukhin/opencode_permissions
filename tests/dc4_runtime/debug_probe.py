#!/usr/bin/env python3
"""Temporary sanitized diagnostics for DC-4 runtime acceptance."""
from __future__ import annotations

import json
import re
import subprocess
import time

import run_probe

_original_assert = run_probe.assert_scenario


def debug_assert(name, trace_events, parts, sentinel):
    summary = {
        "scenario": name,
        "trace": trace_events,
        "tool_states": [
            {
                "status": (part.get("state") or {}).get("status"),
                "output": str((part.get("state") or {}).get("output", ""))[:160],
            }
            for part in parts
        ],
    }
    print("DC4_DIAGNOSTIC=" + json.dumps(summary, sort_keys=True))
    return _original_assert(name, trace_events, parts, sentinel)


def _safe_tail(text: str) -> str:
    lines = text.splitlines()[-20:]
    redacted = []
    for line in lines:
        line = re.sub(r"(?i)(api[_-]?key|token|password|authorization)(\s*[:=]\s*)\S+", r"\1\2<redacted>", line)
        redacted.append(line[:300])
    return "\\n".join(redacted)[-3000:]


def debug_wait_server(base, directory, process):
    started = time.monotonic()
    deadline = started + 60
    last = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            print(
                "DC4_SERVER_DIAGNOSTIC="
                + json.dumps(
                    {
                        "status": "exited",
                        "returncode": process.returncode,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "tail": _safe_tail(output),
                    },
                    sort_keys=True,
                )
            )
            raise RuntimeError(f"OpenCode server exited early with {process.returncode}")
        try:
            run_probe.http_json("GET", base + "/session", directory=directory, timeout=2)
            print(
                "DC4_SERVER_DIAGNOSTIC="
                + json.dumps(
                    {
                        "status": "ready",
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    },
                    sort_keys=True,
                )
            )
            return
        except Exception as exc:
            last = exc
            time.sleep(0.2)

    process.terminate()
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=5)
    print(
        "DC4_SERVER_DIAGNOSTIC="
        + json.dumps(
            {
                "status": "timeout",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "last_error_type": type(last).__name__ if last else None,
                "tail": _safe_tail(output or ""),
            },
            sort_keys=True,
        )
    )
    raise RuntimeError(f"OpenCode server did not become ready: {last}")


run_probe.assert_scenario = debug_assert
run_probe.wait_server = debug_wait_server

if __name__ == "__main__":
    raise SystemExit(run_probe.main())

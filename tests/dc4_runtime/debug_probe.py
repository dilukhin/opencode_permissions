#!/usr/bin/env python3
"""Temporary sanitized diagnostics for DC-4 runtime acceptance."""
from __future__ import annotations

import json
import run_probe

_original = run_probe.assert_scenario


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
    return _original(name, trace_events, parts, sentinel)


run_probe.assert_scenario = debug_assert

if __name__ == "__main__":
    raise SystemExit(run_probe.main())

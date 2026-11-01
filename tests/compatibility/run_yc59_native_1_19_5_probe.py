#!/usr/bin/env python3
"""Observe native Windows permissions on exact OpenCode 1.19.5, without YC.

An automated HTTP fixture answers native prompts. This must never be described
as evidence of human consent or as authorization for a cloud operation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

COMPAT = Path(__file__).resolve().parent
sys.path.insert(0, str(COMPAT))
import run_windows_native_probe as native  # noqa: E402

VERSION = "1.19.5"
SCENARIOS = ("native_allow", "native_deny", "native_ask_once", "native_ask_reject")


def observe(
    opencode: str,
    shell: str,
    *,
    version_probe: Callable[[str], str],
    scenario_runner: Callable[[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    # Unknown versions stop before any session, local provider or test command.
    if version_probe(opencode) != VERSION:
        raise ValueError("YC59_NATIVE_EXACT_VERSION_REQUIRED")
    results = [scenario_runner(opencode, shell, name) for name in SCENARIOS]
    if any(row.get("status") != "PASS" for row in results):
        raise ValueError("YC59_NATIVE_SCENARIO_FAILED")
    return {
        "schema": "yc59-native-observation/v1",
        "opencode_version": VERSION,
        "platform": "windows",
        "scope": "isolated_native_permission_only",
        "result": "NATIVE_OBSERVED_HUMAN_CONSENT_NOT_PROVEN",
        "reply_origin": "automated_http_fixture",
        "human_consent_proven": False,
        "installed_dima_hp_binary_proven": False,
        "yc_authorization_binding_proven": False,
        "cloud_invocations": 0,
        "deployment_authorized": False,
        "results": results,
    }


def binary_version(path: str) -> str:
    result = subprocess.run([path, "--version"], check=True, text=True,
                            capture_output=True, timeout=15)
    return result.stdout.strip()


def main() -> int:
    if os.name != "nt":
        raise SystemExit("YC59_NATIVE_WINDOWS_REQUIRED")
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode", required=True)
    parser.add_argument("--shell", required=True)
    args = parser.parse_args()
    result = observe(args.opencode, args.shell, version_probe=binary_version,
                     scenario_runner=native.run_scenario)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

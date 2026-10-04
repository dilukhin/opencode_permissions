#!/usr/bin/env python3
"""Exercise exact OpenCode 1.18.32 native bash permissions on Windows.

This is a runtime observation gate, not a Windows P0 policy or classifier proof.
All commands only emit a sentinel from an isolated temporary project.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

DC4_DIR = Path(__file__).resolve().parents[1] / "dc4_runtime"
sys.path.insert(0, str(DC4_DIR))
import run_probe as dc4  # noqa: E402


SCENARIOS = {
    "native_allow": ("allow", "OC_WINDOWS_NATIVE_ALLOW"),
    "native_deny": ("deny", "OC_WINDOWS_NATIVE_DENY"),
    "native_ask_once": ("ask", "OC_WINDOWS_NATIVE_ONCE"),
    "native_ask_reject": ("ask", "OC_WINDOWS_NATIVE_REJECT"),
    "compound_diagnostics_allow": ("allow", "OC_WINDOWS_COMPOUND_ALLOW"),
    "compound_diagnostics_ask": ("ask", "OC_WINDOWS_COMPOUND_UNAPPROVED"),
}


def pending(base: str, directory: str, session_id: str) -> list[dict[str, Any]]:
    requests = dc4.http_json("GET", base + "/permission", directory=directory)
    if not isinstance(requests, list):
        raise AssertionError(f"permission list has unexpected shape: {type(requests).__name__}")
    return [item for item in requests if item.get("sessionID") == session_id]


def observe(base: str, directory: str, session_id: str, sentinel: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requests = pending(base, directory, session_id)
    messages = dc4.http_json("GET", base + f"/session/{session_id}/message", directory=directory)
    parts = dc4.tool_parts(messages)
    return requests, parts


def wait_for(base: str, directory: str, session_id: str, sentinel: str, wanted: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deadline = time.monotonic() + 30
    last: tuple[list[dict[str, Any]], list[dict[str, Any]]] = ([], [])
    while time.monotonic() < deadline:
        last = observe(base, directory, session_id, sentinel)
        requests, parts = last
        statuses = [(part.get("state") or {}).get("status") for part in parts]
        if wanted == "pending" and requests:
            return last
        if wanted in statuses:
            return last
        time.sleep(0.2)
    raise AssertionError(
        f"timed out waiting for {wanted}; pending={len(last[0])}; "
        f"states={[(p.get('state') or {}).get('status') for p in last[1]]}"
    )


def assert_no_execution(parts: list[dict[str, Any]], sentinel: str) -> None:
    if any(
        sentinel in str((part.get("state") or {}).get("output", ""))
        for part in parts
        if (part.get("state") or {}).get("status") == "completed"
    ):
        raise AssertionError("blocked command produced execution sentinel")


def assert_execution(parts: list[dict[str, Any]], sentinel: str) -> None:
    if not any(
        (part.get("state") or {}).get("status") == "completed"
        and sentinel in str((part.get("state") or {}).get("output", ""))
        for part in parts
    ):
        raise AssertionError("allowed command did not produce execution sentinel")


def run_scenario(opencode: str, shell: str, name: str) -> dict[str, Any]:
    action, sentinel = SCENARIOS[name]
    diagnostic = name.startswith("compound_diagnostics_")
    command = (
        "Get-Date -Format o; [System.Environment]::OSVersion.VersionString; "
        f"Get-Location; Write-Output {sentinel}"
        if diagnostic else f"Write-Output {sentinel}"
    )
    rules = [
        {"permission": "bash", "pattern": "Get-Date -Format o", "action": "allow"},
        {"permission": "bash", "pattern": "[System.Environment]::OSVersion.VersionString", "action": "allow"},
        {"permission": "bash", "pattern": "Get-Location", "action": "allow"},
    ] if diagnostic else []
    if action == "allow" or not diagnostic:
        rules.append({"permission": "bash", "pattern": f"Write-Output {sentinel}", "action": action})
    with tempfile.TemporaryDirectory(prefix=f"opencode-windows-{name}-") as tmp, dc4.mock_provider(command) as provider_port:
        root = Path(tmp)
        project = root / "project"
        home = root / "home"
        project.mkdir()
        home.mkdir()
        config = {
            "$schema": "https://opencode.ai/config.json",
            "shell": shell,
            "provider": {
                "dc4": {
                    "name": "Local Mock",
                    "npm": "@ai-sdk/openai-compatible",
                    "api": f"http://127.0.0.1:{provider_port}/v1",
                    "models": {
                        "mock": {
                            "name": "Mock",
                            "tool_call": True,
                            "limit": {"context": 32000, "output": 4096},
                        }
                    },
                    "options": {
                        "apiKey": "synthetic-local-test",
                        "baseURL": f"http://127.0.0.1:{provider_port}/v1",
                    },
                }
            },
        }
        if diagnostic:
            config["permission"] = {"bash": {
                "*": "ask",
                **{rule["pattern"]: rule["action"] for rule in rules},
            }}
        (project / "opencode.json").write_text(json.dumps(config), encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CACHE_HOME": str(home / ".cache"),
        })
        env.pop("OPENCODE_SERVER_PASSWORD", None)
        port = dc4.free_port()
        server = subprocess.Popen(
            [opencode, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
            cwd=project,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            dc4.wait_server(base, str(project), server)
            session = dc4.http_json(
                "POST", base + "/session", directory=str(project),
                payload={"title": name} if diagnostic else {"title": name, "permission": rules},
            )
            session_id = session["id"]
            dc4.http_json(
                "POST", base + f"/session/{session_id}/prompt_async", directory=str(project),
                payload={
                    "agent": "build",
                    "model": {"providerID": "dc4", "modelID": "mock"},
                    "parts": [{"type": "text", "text": f"Windows native permission proof {name}"}],
                }, timeout=10,
            )
            wanted = "pending" if action == "ask" else "completed" if action == "allow" else "error"
            requests, parts = wait_for(base, str(project), session_id, sentinel, wanted)
            if action == "ask":
                if len(requests) != 1 or requests[0].get("permission") != "bash" or requests[0].get("metadata", {}).get("command") != command:
                    raise AssertionError(f"{name}: expected one correlated bash permission request")
                assert_no_execution(parts, sentinel)
                if diagnostic and f"Write-Output {sentinel}" not in requests[0].get("patterns", []):
                    raise AssertionError(f"{name}: unmatched suffix was not included in permission patterns")
                reply = "once" if name == "native_ask_once" else "reject"
                dc4.http_json(
                    "POST", base + f"/permission/{requests[0]['id']}/reply",
                    directory=str(project), payload={"reply": reply},
                )
                _, parts = wait_for(
                    base, str(project), session_id, sentinel,
                    "completed" if reply == "once" else "error",
                )
                if pending(base, str(project), session_id):
                    raise AssertionError(f"{name}: permission remained pending after {reply}")
            elif requests:
                raise AssertionError(f"{name}: native {action} left a permission pending")
            if diagnostic and name == "compound_diagnostics_allow":
                if not any(
                    (part.get("state") or {}).get("status") == "completed"
                    and (part.get("state") or {}).get("metadata", {}).get("exit") == 0
                    for part in parts
                ):
                    raise AssertionError(f"{name}: diagnostic command did not exit successfully")

            if name in {"native_allow", "native_ask_once", "compound_diagnostics_allow"}:
                assert_execution(parts, sentinel)
            else:
                assert_no_execution(parts, sentinel)
            return {"scenario": name, "status": "PASS", "decision": action}
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def main() -> int:
    if os.name != "nt":
        raise SystemExit("Windows native proof must run on Windows")
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode", required=True)
    parser.add_argument("--shell", required=True)
    args = parser.parse_args()
    version = subprocess.run([args.opencode, "--version"], check=True, text=True, capture_output=True).stdout.strip()
    if version != "1.18.32":
        raise SystemExit(f"expected exact OpenCode 1.18.32, got {version!r}")
    results = [run_scenario(args.opencode, args.shell, name) for name in SCENARIOS]
    print(json.dumps({
        "schema": "opencode-windows-native-runtime-proof/v1",
        "opencode_version": version,
        "platform": "windows",
        "scope": "native_permission_only",
        "results": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

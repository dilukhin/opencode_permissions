#!/usr/bin/env python3
"""Run the non-destructive DC-4 exact OpenCode 1.18.26 integration proof."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any

SCENARIOS = {
    "native_allow": ("allow", "/usr/bin/printf DC4_NATIVE_ALLOW", "DC4_NATIVE_ALLOW"),
    "native_deny": ("deny", "/usr/bin/printf DC4_NATIVE_DENY", "DC4_NATIVE_DENY"),
    "classifier_allow": ("ask", "/usr/bin/printf DC4_CLASSIFIER_ALLOW", "DC4_CLASSIFIER_ALLOW"),
    "classifier_env_drift": ("ask", "/usr/bin/printf DC4_DRIFT_BLOCK", "DC4_DRIFT_BLOCK"),
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class MockHandler(BaseHTTPRequestHandler):
    command = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size) or b"{}")
        messages = body.get("messages") or []
        has_tool_result = any(isinstance(item, dict) and item.get("role") == "tool" for item in messages)
        has_bash_tool = any(
            isinstance(tool, dict)
            and isinstance(tool.get("function"), dict)
            and tool["function"].get("name") == "bash"
            for tool in (body.get("tools") or [])
        )

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()

        if has_bash_tool and not has_tool_result:
            arguments = json.dumps({"command": self.command}, separators=(",", ":"))
            chunks = [
                {
                    "id": "chatcmpl-dc4",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "mock",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_dc4",
                                        "type": "function",
                                        "function": {"name": "bash", "arguments": arguments},
                                    }
                                ],
                            },
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl-dc4",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "mock",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                },
            ]
        else:
            chunks = [
                {
                    "id": "chatcmpl-dc4-final",
                    "object": "chat.completion.chunk",
                    "created": 2,
                    "model": "mock",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "done"},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl-dc4-final",
                    "object": "chat.completion.chunk",
                    "created": 2,
                    "model": "mock",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            ]

        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@contextmanager
def mock_provider(command: str):
    port = free_port()
    handler = type("ScenarioMockHandler", (MockHandler,), {"command": command})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def http_json(
    method: str,
    url: str,
    *,
    directory: str,
    payload: Any | None = None,
    timeout: int = 30,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"x-opencode-directory": directory}
    if data is not None:
        headers["content-type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {body}") from exc
    if not raw:
        return None
    return json.loads(raw)


def wait_server(base: str, directory: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    last = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"OpenCode server exited early with {process.returncode}")
        try:
            http_json("GET", base + "/session", directory=directory, timeout=2)
            return
        except Exception as exc:
            last = exc
            time.sleep(0.2)
    raise RuntimeError(f"OpenCode server did not become ready: {last}")


def events(trace: Path) -> list[dict[str, Any]]:
    if not trace.exists():
        return []
    return [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]


def tool_parts(messages: Any) -> list[dict[str, Any]]:
    result = []
    if not isinstance(messages, list):
        return result
    for message in messages:
        if not isinstance(message, dict):
            continue
        for part in message.get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "tool" and part.get("tool") == "bash":
                result.append(part)
    return result


def assert_scenario(
    name: str,
    trace_events: list[dict[str, Any]],
    parts: list[dict[str, Any]],
    sentinel: str,
) -> None:
    names = [item.get("event") for item in trace_events]
    if names.count("tool_before") != 1:
        raise AssertionError(f"{name}: expected exactly one tool_before, got {names}")

    completed = [p for p in parts if (p.get("state") or {}).get("status") == "completed"]
    sentinel_completed = any(
        sentinel in str((p.get("state") or {}).get("output", "")) for p in completed
    )

    if name == "native_allow":
        forbidden = {
            "permission_asked",
            "classifier_result",
            "permission_reply_once",
            "shell_env_guard_pass",
        }
        if forbidden.intersection(names):
            raise AssertionError(f"native_allow: classifier/ASK path unexpectedly observed: {names}")
        if names.count("shell_env_native_passthrough") != 1 or names.count("tool_after") != 1:
            raise AssertionError(f"native_allow: expected native execution path: {names}")
        if not sentinel_completed or not any(
            e.get("event") == "tool_after" and e.get("outputMatched") for e in trace_events
        ):
            raise AssertionError("native_allow: execution sentinel missing")
        return

    if name == "native_deny":
        forbidden = {
            "permission_asked",
            "classifier_result",
            "permission_reply_once",
            "shell_env_guard_pass",
            "shell_env_native_passthrough",
            "tool_after",
        }
        if forbidden.intersection(names):
            raise AssertionError(f"native_deny: operation advanced past terminal native DENY: {names}")
        if sentinel_completed:
            raise AssertionError("native_deny: denied sentinel executed")
        return

    required_prefix = ["tool_before", "permission_asked", "classifier_result", "permission_reply_once"]
    for required in required_prefix:
        if names.count(required) != 1:
            raise AssertionError(f"{name}: missing/duplicate {required}: {names}")
    classifier = next(e for e in trace_events if e.get("event") == "classifier_result")
    if classifier.get("decision") != "ALLOW" or not str(
        classifier.get("operationIdentity", "")
    ).startswith("sha256:"):
        raise AssertionError(f"{name}: classifier result is not exact ALLOW: {classifier}")

    if name == "classifier_allow":
        if names.count("shell_env_guard_pass") != 1 or names.count("tool_after") != 1:
            raise AssertionError(f"classifier_allow: guard/execution path incomplete: {names}")
        if not sentinel_completed or not any(
            e.get("event") == "tool_after" and e.get("outputMatched") for e in trace_events
        ):
            raise AssertionError("classifier_allow: execution sentinel missing")
        return

    if name == "classifier_env_drift":
        rejects = [e for e in trace_events if e.get("event") == "shell_env_guard_reject"]
        if len(rejects) != 1 or rejects[0].get("reason") != "environment_drift":
            raise AssertionError(
                f"classifier_env_drift: expected environment guard rejection: {trace_events}"
            )
        if "shell_env_guard_pass" in names or "tool_after" in names or sentinel_completed:
            raise AssertionError(f"classifier_env_drift: command advanced after drift: {names}")
        return

    raise AssertionError(f"unknown scenario {name}")


def run_scenario(opencode: str, repo_root: Path, name: str) -> dict[str, Any]:
    action, command, sentinel = SCENARIOS[name]
    with tempfile.TemporaryDirectory(prefix=f"dc4-{name}-") as tmp, mock_provider(command) as provider_port:
        root = Path(tmp)
        project = root / "project"
        home = root / "home"
        project.mkdir()
        home.mkdir()
        plugin_dir = project / ".opencode" / "plugins"
        plugin_dir.mkdir(parents=True)
        shutil.copy2(
            repo_root / "tests" / "dc4_runtime" / "dc4_plugin.js",
            plugin_dir / "dc4_plugin.js",
        )
        trace = root / "trace.jsonl"

        config = {
            "$schema": "https://opencode.ai/config.json",
            "shell": "/bin/dash",
            "provider": {
                "dc4": {
                    "name": "DC4 Local Mock",
                    "npm": "@ai-sdk/openai-compatible",
                    "api": f"http://127.0.0.1:{provider_port}/v1",
                    "models": {
                        "mock": {
                            "name": "DC4 Mock",
                            "tool_call": True,
                            "limit": {"context": 32000, "output": 4096},
                        }
                    },
                    "options": {
                        "apiKey": "dc4-local-test",
                        "baseURL": f"http://127.0.0.1:{provider_port}/v1",
                    },
                }
            },
        }
        (project / "opencode.json").write_text(json.dumps(config), encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
                "XDG_CACHE_HOME": str(home / ".cache"),
                "DC4_REPO_ROOT": str(repo_root),
                "DC4_TRACE": str(trace),
                "DC4_PYTHON": os.environ.get("PYTHON", os.sys.executable),
                "DC4_SCENARIO": name,
                "DC4_WORKSPACE_ROOT": str(project),
                "DC4_EXPECT_SENTINEL": sentinel,
            }
        )
        env.pop("OPENCODE_SERVER_PASSWORD", None)

        port = free_port()
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
            wait_server(base, str(project), server)
            session_rule = {"permission": "bash", "pattern": command, "action": action}
            session = http_json(
                "POST",
                base + "/session",
                directory=str(project),
                payload={"title": f"DC4 {name}", "permission": [session_rule]},
            )
            session_id = session["id"]
            http_json(
                "POST",
                base + f"/session/{session_id}/message",
                directory=str(project),
                payload={
                    "agent": "build",
                    "model": {"providerID": "dc4", "modelID": "mock"},
                    "parts": [{"type": "text", "text": f"DC4 runtime proof {name}"}],
                },
                timeout=45,
            )
            messages = http_json(
                "GET",
                base + f"/session/{session_id}/message",
                directory=str(project),
            )
            trace_events = events(trace)
            parts = tool_parts(messages)
            assert_scenario(name, trace_events, parts, sentinel)
            return {
                "scenario": name,
                "status": "PASS",
                "events": [e.get("event") for e in trace_events],
                "tool_states": [(p.get("state") or {}).get("status") for p in parts],
            }
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    version = subprocess.run(
        [args.opencode, "--version"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if version != "1.18.26":
        raise SystemExit(f"DC-4 requires exact OpenCode 1.18.26, got {version!r}")

    results = [run_scenario(args.opencode, repo_root, name) for name in SCENARIOS]
    print(
        json.dumps(
            {"schema": "dc4-runtime-proof/v1", "opencode_version": version, "results": results},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

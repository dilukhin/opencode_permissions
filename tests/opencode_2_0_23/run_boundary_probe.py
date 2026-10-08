"""Опыт на собранном OpenCode 2.0.23: API и child, без удалённых мутаций."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

SOURCE_SHA = "0fd7e2829449b052abf0078666669302923d77af"
VERSION = "2.0.23"


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def http(base, password, method, path, payload=None):
    headers = {"content-type": "application/json"}
    if password is not None:
        headers["authorization"] = "Basic " + base64.b64encode(("opencode:" + password).encode()).decode()
    request = urllib.request.Request(
        base + path, data=None if payload is None else json.dumps(payload).encode(),
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        # Тело ответа не выводится и не включается в evidence.
        return error.code, None


def stream_lines(stream, messages):
    for line in stream:
        messages.put(line)


def wait_address(process, messages):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        require(process.poll() is None, "SERVER_EXITED_BEFORE_LISTEN")
        try:
            line = messages.get(timeout=0.2)
        except queue.Empty:
            continue
        match = re.search(r"server listening on (http://127\.0\.0\.1:\d+)", line)
        if match:
            return match.group(1)
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("url"), str):
            require(re.fullmatch(r"http://127\.0\.0\.1:\d+", value["url"]), "NON_LOOPBACK_SERVER")
            return value["url"]
    raise RuntimeError("SERVER_LISTEN_TIMEOUT")


def session(base, password, directory, effect="ask"):
    status, body = http(base, password, "POST", "/api/session", {
        "title": "isolated sudo-job permission probe",
        "location": {"directory": str(directory)},
        "permissions": [{"action": "sudo_job.*", "resource": "*", "effect": effect}],
    })
    require(status == 200 and isinstance(body, dict), "SESSION_CREATE_FAILED")
    return body["data"]["id"]


def ask(base, password, session_id, action="sudo_job.start"):
    status, body = http(base, password, "POST", f"/api/session/{session_id}/permission", {
        "action": action, "resources": ["sha256:synthetic-operation"], "save": [],
        "metadata": {"scope": "synthetic-no-execution"},
    })
    require(status == 200 and isinstance(body, dict), "PERMISSION_CREATE_FAILED")
    return body["data"]


def reply(base, password, session_id, request_id, decision="once"):
    return http(base, password, "POST", f"/api/session/{session_id}/permission/{request_id}/reply",
                {"decision": decision})[0]


def pending_ids(base, password, session_id):
    status, body = http(base, password, "GET", f"/api/session/{session_id}/permission")
    require(status == 200 and isinstance(body, dict), "PERMISSION_LIST_FAILED")
    return [item["id"] for item in body["data"]]


def probe(binary, mode, shell_fixture=None):
    with tempfile.TemporaryDirectory(prefix=f"opencode-2-boundary-{mode}-") as temporary:
        root = Path(temporary)
        home = root / "home"
        project = root / "project"
        config = root / "config"
        for directory in (home, project, config):
            directory.mkdir(mode=0o700)
        password = secrets.token_urlsafe(32)
        # Сервер получает исключительно синтетический credential. GitHub/LLM/SSH
        # credentials родителя не наследуются и не читаются через /proc.
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home),
            "XDG_CONFIG_HOME": str(root / "xdg-config"), "XDG_DATA_HOME": str(root / "xdg-data"),
            "XDG_CACHE_HOME": str(root / "xdg-cache"), "XDG_STATE_HOME": str(root / "xdg-state"),
            "OPENCODE_CONFIG_DIR": str(config), "OPENCODE_PASSWORD": password,
            "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_FILEWATCHER": "1",
            "OPENCODE_DISABLE_FFF": "1", "OPENCODE_CONFIG_PROJECT_DISABLE": "1",
        }
        command = [str(binary), "serve", "--hostname", "127.0.0.1", "--port", "0"]
        if mode == "stdio":
            command.append("--stdio")
        child_script = Path(__file__).with_name("child_reply_probe.py").resolve()
        child_extra = []
        process_options = {}
        if shell_fixture is not None:
            child_script, child_extra, process_options = shell_fixture.configure(root, environment, binary)
        process = subprocess.Popen(command, cwd=project, env=environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                   **process_options)
        messages = queue.Queue()
        reader = threading.Thread(target=stream_lines, args=(process.stdout, messages), daemon=True)
        reader.start()
        try:
            base = wait_address(process, messages)
            require(http(base, None, "GET", "/api/session")[0] == 401, "MISSING_AUTH_NOT_REJECTED")
            target = session(base, password, project)
            other = session(base, password, project)
            start = ask(base, password, target)
            require(start["effect"] == "ask", "START_DID_NOT_ASK")
            require(reply(base, password, other, start["id"]) == 404, "CROSS_SESSION_REPLY_ACCEPTED")
            require(start["id"] in pending_ids(base, password, target), "MISMATCH_CONSUMED_PERMISSION")

            # Это настоящий child из Session.shell, с фактическим Shell.environment
            # данной версии. Пароль не передаётся в argv или input child.
            output = project / "child-result.json"
            child_command = shlex.join([
                sys.executable, str(child_script), "--url", base, "--server-pid", str(process.pid),
                "--session", target, "--request", start["id"], "--output", str(output),
            ] + child_extra)
            status, _ = http(base, password, "POST", f"/api/session/{other}/shell", {"command": child_command})
            require(status == 204, "SHELL_CHILD_ADMISSION_FAILED")
            deadline = time.monotonic() + 15
            while not output.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            require(output.exists(), "SHELL_CHILD_RESULT_MISSING")
            child = json.loads(output.read_text(encoding="utf-8"))
            if shell_fixture is not None:
                shell_fixture.verify(child)
            remaining = pending_ids(base, password, target)
            if child["reply_accepted"]:
                require(start["id"] not in remaining, "CHILD_REPLY_DID_NOT_CONSUME")
            else:
                require(start["id"] in remaining, "PERMISSION_DISAPPEARED_WITHOUT_REPLY")
                require(reply(base, password, target, start["id"]) == 204, "SCRIPTED_ONCE_FAILED")
            require(reply(base, password, target, start["id"]) == 404, "REPLAY_ACCEPTED")

            rejected = ask(base, password, target)
            require(rejected["effect"] == "ask", "SECOND_START_WAS_AUTO_ALLOWED")
            require(reply(base, password, target, rejected["id"], "reject") == 204, "REJECT_FAILED")
            require(rejected["id"] not in pending_ids(base, password, target), "REJECT_NOT_CONSUMED")
            denied_session = session(base, password, project, "deny")
            denied = ask(base, password, denied_session)
            require(denied["effect"] == "deny", "CONFIGURED_DENY_IGNORED")
            require(pending_ids(base, password, denied_session) == [], "DENY_QUEUED_PERMISSION")

            start = ask(base, password, target)
            stop = ask(base, password, target, "sudo_job.stop")
            require(start["effect"] == stop["effect"] == "ask", "START_STOP_DID_NOT_ASK")
            require(reply(base, password, target, start["id"]) == 204, "START_ONCE_FAILED")
            require(stop["id"] in pending_ids(base, password, target), "START_APPROVED_STOP")
            require(reply(base, password, target, stop["id"], "reject") == 204, "STOP_REJECT_FAILED")
            status, saved = http(base, password, "GET", "/api/permission/saved")
            require(status == 200 and saved["data"] == [], "ONE_TIME_REPLY_SAVED_APPROVAL")
            plugin = shell_fixture.probe_plugin(base, password, target, other) if shell_fixture is not None else None
            return {"mode": mode, "missing_auth_rejected": True, "cross_session_rejected": True,
                    "replay_rejected": True, "reject_observed": True, "deny_observed": True,
                    "separate_stop_observed": True, "saved_approvals_empty": True,
                    "child": child, "plugin": plugin,
                    "reply_source": "scripted API / synthetic child or fixture plugin, not human UI"}
        finally:
            # Завершается только созданный этим опытом process object.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
            if shell_fixture is not None:
                shell_fixture.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    version = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=15)
    require(version.returncode == 0 and version.stdout.strip() == f"opencode v{VERSION}", "BINARY_VERSION_MISMATCH")
    package = json.loads((args.source / "package.json").read_text())
    require(package["version"] == VERSION, "SOURCE_VERSION_MISMATCH")
    result = {
        "schema": "opencode-2-boundary-probe/v1", "version": VERSION, "source_sha": SOURCE_SHA,
        "binary_kind": "CI source build without embedded web UI; not installed official release",
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "lock_sha256": hashlib.sha256((args.source / "bun.lock").read_bytes()).hexdigest(),
        "bun_requirement": package["packageManager"], "remote_mutations": False,
        "actual_human_ui_proof": False, "untrusted_plugin_runtime_proof": False,
        "native_sudo_job_admission_ready": False,
        "modes": [probe(binary, mode) for mode in ("default", "stdio")],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"probe_completed": True, "native_sudo_job_admission_ready": False,
                      "child_can_reply": {item["mode"]: item["child"]["reply_accepted"] for item in result["modes"]}}))


if __name__ == "__main__":
    main()

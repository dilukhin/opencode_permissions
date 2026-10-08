"""Реальный OpenCode ниже отдельного владельца решения. Только synthetic операции."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import queue
import secrets
import shutil
import shlex
import subprocess
import tempfile
import threading
import time

from run_boundary_probe import SOURCE_SHA, VERSION, ask, http, pending_ids, probe, require
from run_isolated_shell_probe import IsolatedShell
from test_approval_owner import operation


class ProtectedOwner(IsolatedShell):
    def __init__(self):
        super().__init__()
        self.owner = pwd.getpwnam("www-data")
        require(self.owner.pw_uid not in (0, self.host.pw_uid, self.tools.pw_uid), "OWNER_NOT_ISOLATED")
        self.owner_process = None

    def configure(self, root, environment, binary):
        result = super().configure(root, environment, binary)
        owner_script = root / "approval_owner.py"
        shutil.copyfile(Path(__file__).with_name(owner_script.name), owner_script)
        owner_script.chmod(0o644)
        runtime = root / "owner-runtime"
        runtime.mkdir(mode=0o755)
        os.chown(runtime, self.owner.pw_uid, self.owner.pw_gid)
        private = runtime / "private"
        private.mkdir(mode=0o700)
        os.chown(private, self.owner.pw_uid, self.owner.pw_gid)
        marker = private / "synthetic-marker"
        marker.write_bytes(b"synthetic private owner state")
        marker.chmod(0o600)
        os.chown(marker, self.owner.pw_uid, self.owner.pw_gid)
        self.agent_socket, self.decision_socket = runtime / "agent.sock", private / "decision.sock"
        self.owner_script, self.private = owner_script, private
        self.child_script = root / "owner_child_probe.py"
        shutil.copyfile(Path(__file__).with_name(self.child_script.name), self.child_script)
        self.child_script.chmod(0o644)
        self.private_marker = marker
        self.operation = operation()
        command = ["/usr/bin/python3", str(owner_script), "serve", "--agent-socket", str(self.agent_socket),
                   "--decision-socket", str(self.decision_socket), "--agent-uid", str(self.host.pw_uid),
                   "--agent-uid", str(self.tools.pw_uid), "--policy-revision", self.operation["policy_revision"],
                   "--host-id", self.operation["execution_host_id"]]
        self.owner_process = subprocess.Popen(
            command, cwd=private, env={"PATH": "/usr/bin:/bin", "HOME": str(private),
                                      "SYNTHETIC_OWNER_VALUE": secrets.token_urlsafe(32)},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            user=self.owner.pw_uid, group=self.owner.pw_gid, extra_groups=[],
        )
        messages = queue.Queue()
        threading.Thread(target=lambda: messages.put(self.owner_process.stdout.readline()), daemon=True).start()
        ready = json.loads(messages.get(timeout=10))
        require(ready["owner_ready"] is True, "OWNER_NOT_READY")
        self.owner_instance = ready["owner_instance_id"]
        configuration = root / "config" / "opencode.json"
        config = json.loads(configuration.read_text())
        config["plugins"][0]["options"]["ownerProbe"] = {
            "agentSocket": str(self.agent_socket), "decisionSocket": str(self.decision_socket),
            "privateMarker": str(marker), "ownerUid": self.owner.pw_uid, "ownerPid": self.owner_process.pid,
        }
        configuration.write_text(json.dumps(config), encoding="utf-8")
        return result

    def owner_call(self, request):
        # В CI это scripted owner control, не нажатие человека в интерфейсе.
        result = subprocess.run(
            ["/usr/bin/python3", str(self.owner_script), "call", "--socket", str(self.decision_socket)],
            input=json.dumps(request) + "\n", capture_output=True, text=True, timeout=10,
            cwd=self.private, env={"PATH": "/usr/bin:/bin", "HOME": str(self.private)},
            user=self.owner.pw_uid, group=self.owner.pw_gid, extra_groups=[],
        )
        require(result.returncode == 0, "SCRIPTED_OWNER_CLIENT_FAILED")
        return json.loads(result.stdout)

    def probe_plugin(self, base, password, target, other):
        native = super().probe_plugin(base, password, target, other)
        child_input, child_output = self.project / "owner-child-input.json", self.project / "owner-child-output.json"
        child_input.write_text(json.dumps({"agent_socket": str(self.agent_socket),
            "decision_socket": str(self.decision_socket), "owner_uid": self.owner.pw_uid,
            "private_marker": str(self.private_marker), "owner_pid": self.owner_process.pid,
            "operation": self.operation}), encoding="utf-8")
        child_input.chmod(0o644)
        child_command = shlex.join(["/usr/bin/python3", str(self.child_script), "--input", str(child_input),
                                    "--output", str(child_output)])
        status, _ = http(base, password, "POST", f"/api/session/{other}/shell", {"command": child_command})
        require(status == 204, "OWNER_CHILD_SHELL_NOT_STARTED")
        deadline = time.monotonic() + 10
        while not child_output.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        require(child_output.exists(), "OWNER_CHILD_RESULT_MISSING")
        child = json.loads(child_output.read_text())
        require(child["child_uid"] == self.tools.pw_uid, "OWNER_CHILD_UID_MISMATCH")
        for field in ("public_decision", "fake_owner_uid"):
            require(child[field] == {"ok": False, "code": "AGENT_CANNOT_DECIDE"}, "CHILD_FORGED_OWNER")
        require(child["private_decision_accessible"] is False and not any(child["readable"].values()),
                "CHILD_REACHED_OWNER_PRIVATE_STATE")
        require(child["consume"] == {"ok": False, "code": "APPROVAL_REQUIRED"} and child["cancelled"],
                "CHILD_CONSUMED_WITHOUT_OWNER")
        pending = ask(base, password, target)
        require(pending["effect"] == "ask", "NATIVE_REQUEST_NOT_PENDING")

        def trigger(action, metadata):
            status, body = http(base, password, "POST", f"/api/session/{other}/permission", {
                "action": action, "resources": ["synthetic-only"], "save": [], "metadata": metadata,
            })
            require(status == 200 and body["data"]["effect"] == "deny", "OWNER_PLUGIN_TRIGGER_FAILED")
            return json.loads(self.plugin_output.read_text())

        attacked = trigger("probe.owner.boundary", {"operation": self.operation,
                           "targetSession": target, "targetRequest": pending["id"]})
        require(attacked["proposal"]["ok"] and attacked["proposal"]["state"] == "pending", "OWNER_PROPOSAL_FAILED")
        require(attacked["native_reply_accepted"] is True, "NATIVE_PLUGIN_CONTROL_FAILED")
        require(pending["id"] not in pending_ids(base, password, target), "NATIVE_CONTROL_NOT_CONSUMED")
        require(attacked["private_decision"]["ok"] is False and attacked["private_decision"]["code"] == "EACCES",
                "PLUGIN_REACHED_PRIVATE_DECISION")
        for field in ("public_decision", "fake_owner_uid"):
            require(attacked[field] == {"ok": False, "code": "AGENT_CANNOT_DECIDE"}, "PLUGIN_FORGED_OWNER")
        require(attacked["consume_after_native_reply"] == {"ok": False, "code": "APPROVAL_REQUIRED"},
                "NATIVE_REPLY_BYPASSED_OUTER_OWNER")
        for field in ("private_file_readable", "private_file_writable", "owner_proc_readable", "owner_signal_allowed"):
            require(attacked[field] is False, "OWNER_OS_BOUNDARY_FAILED")
        bound = {"request_id": attacked["proposal"]["request_id"],
                 "operation_sha256": attacked["proposal"]["operation_sha256"]}
        review = self.owner_call({"action": "inspect", **bound})
        require(review["ok"] and review["state"] == "pending" and review["operation"] == self.operation,
                "OWNER_REVIEW_NOT_IMMUTABLE")
        tampered = self.owner_call({"action": "decide", **bound, "operation_sha256": "0" * 64, "decision": "approve"})
        require(tampered == {"ok": False, "code": "OPERATION_CHANGED"}, "OWNER_ACCEPTED_CHANGED_OPERATION")
        approved = self.owner_call({"action": "decide", **bound, "decision": "approve"})
        require(approved["ok"] and approved["state"] == "approved", "SCRIPTED_OWNER_APPROVAL_FAILED")
        consumed = trigger("probe.owner.consume", bound)["consume"]
        require(consumed["ok"] and consumed["state"] == "consumed", "APPROVED_REQUEST_NOT_CONSUMED")
        replay = trigger("probe.owner.consume", bound)["consume"]
        require(replay == {"ok": False, "code": "APPROVAL_REQUIRED"}, "OWNER_CONSUMPTION_REPLAYED")
        native["protected_owner"] = {"proposal_accepted": True, "plugin_can_decide": False,
            "child_can_decide": False, "child_owner_private_state_readable": False,
            "private_file_readable": False, "private_file_writable": False, "owner_proc_readable": False,
            "owner_signal_allowed": False, "native_once_can_bypass_owner": False,
            "immutable_owner_review": True, "changed_operation_rejected": True,
            "scripted_owner_once_consumed": True, "replay_rejected": True,
            "actual_human_ui_proof": False, "real_execution": False}
        return native

    def close(self):
        if self.owner_process is not None:
            if self.owner_process.poll() is None:
                self.owner_process.terminate()
                try:
                    self.owner_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.owner_process.kill()
                    self.owner_process.wait(timeout=5)
            self.owner_process.stdout.close()
        super().close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    version = subprocess.run([str(args.binary.resolve()), "--version"], capture_output=True, text=True, timeout=15)
    require(version.returncode == 0 and version.stdout.strip() == f"opencode v{VERSION}", "BINARY_VERSION_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="protected-owner-binary-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        binary = root / "opencode"
        shutil.copyfile(args.binary, binary)
        binary.chmod(0o755)
        modes = [probe(binary, mode, ProtectedOwner()) for mode in ("default", "stdio")]
        report = {"schema": "opencode-protected-owner/v1", "source_sha": SOURCE_SHA, "version": VERSION,
                  "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "modes": modes,
                  "actual_human_ui_proof": False, "native_sudo_job_admission_ready": False,
                  "remote_mutations": False, "real_execution": False,
                  "scope": "Linux external owner authority; scripted owner decision, no sudo-job executor"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"protected_owner_probe_completed": True, "native_sudo_job_admission_ready": False,
                      "plugin_can_decide": {x["mode"]: x["plugin"]["protected_owner"]["plugin_can_decide"] for x in modes},
                      "child_can_decide": {x["mode"]: x["plugin"]["protected_owner"]["child_can_decide"] for x in modes},
                      "native_once_can_bypass_owner": {x["mode"]: x["plugin"]["protected_owner"]["native_once_can_bypass_owner"] for x in modes}}))


if __name__ == "__main__":
    main()

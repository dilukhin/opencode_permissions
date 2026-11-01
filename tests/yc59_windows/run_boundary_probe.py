"""Synthetic OS-account boundary test, allowed ONLY on an ephemeral hosted CI VM.

Creates one temporary non-admin account; deletes only that account in finally.
No YC, SSH, OpenCode, services, scheduled tasks or real operation executor.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid

PINS = Path(__file__).with_name("pins.json")


def load_core(path):
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != pins["owner_core_sha256"]:
        raise ValueError("OWNER_CORE_DIGEST_MISMATCH")
    spec = importlib.util.spec_from_file_location("yc59_existing_owner_core", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_hosted_ci():
    if (os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise RuntimeError("EPHEMERAL_GITHUB_HOSTED_WINDOWS_REQUIRED")


def expect(value, **fields):
    if any(value.get(key) != item for key, item in fields.items()):
        raise AssertionError("BOUNDARY_ASSERTION_FAILED: " + json.dumps({"expected": fields, "actual": value}))
    return value


def run_probe(core_path):
    require_hosted_ci()
    import pipe_transport as pipe
    from windows_account import TemporaryAccount

    core = load_core(core_path)
    owner_sid = pipe.current_sid()
    checks = []
    # Account and files exist only on the disposable CI VM, never the installed host.
    with TemporaryAccount() as account:
        if owner_sid == account.sid:
            raise AssertionError("DISTINCT_ACCOUNT_REQUIRED")
        root = Path(tempfile.mkdtemp(prefix="yc59-", dir=os.environ["PUBLIC"]))
        try:
            subprocess.run(["icacls.exe", str(root), "/inheritance:r", "/grant:r",
                            f"*{owner_sid}:(OI)(CI)F", f"*{account.sid}:(OI)(CI)RX",
                            "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
            for name in ("run_boundary_probe.py", "pipe_transport.py"):
                shutil.copyfile(Path(__file__).with_name(name), root / name)
            exchange = root / "exchange"
            exchange.mkdir()
            subprocess.run(["icacls.exe", str(exchange), "/grant:r", f"*{account.sid}:(OI)(CI)M"],
                           check=True, capture_output=True)
            policy, host = "synthetic-owner-policy/v1", str(uuid.uuid4())
            server = pipe.Server(core, owner_sid, account.sid, policy, host, "yc59-" + uuid.uuid4().hex)
            sequence = 0

            def agent(request, *, private=False, expected_pid=None):
                nonlocal sequence
                sequence += 1
                request_path = exchange / f"request-{sequence}.json"
                result_path = exchange / f"result-{sequence}.json"
                request_path.write_text(json.dumps({"address": server.addresses["decision" if private else "agent"],
                    "pid": os.getpid() if expected_pid is None else expected_pid, "request": request}), encoding="utf-8")
                account.run([sys.executable, str(root / "run_boundary_probe.py"), "client",
                             "--request", str(request_path), "--output", str(result_path)], exchange)
                value = json.loads(result_path.read_text(encoding="utf-8"))
                if value.pop("client_sid") != account.sid:
                    raise AssertionError("CLIENT_KERNEL_SID_MISMATCH")
                return value

            def owner(request):
                return pipe.call(server.addresses["decision"], request, os.getpid())

            command = "synthetic operation never executed"
            executable = str(root / "nonexistent-fixture.exe")
            operation = {"schema": 1, "action": "sudo_job.start", "job_id": str(uuid.uuid4()),
                "transaction_id": str(uuid.uuid4()), "command": command,
                "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                "argv": [executable, "fixture-only"], "executable": executable, "cwd": str(root),
                "ssh_identity": {"remote_host": "fixture.invalid", "remote_port": 22, "remote_user": "fixture",
                    "host_key_algorithm": "ssh-ed25519", "remote_host_key_sha256": "SHA256:" + "A" * 43,
                    "daemon_instance_id": "synthetic", "connection_generation": 1},
                "policy_revision": policy, "execution_host_id": host}
            proposal = expect(agent({"action": "propose", "operation": operation}), ok=True, state="pending")
            bound = {key: proposal[key] for key in ("request_id", "operation_sha256")}
            checks.append("distinct_account_propose_pending")
            expect(agent({"action": "consume", **bound}), ok=False, code="APPROVAL_REQUIRED")
            expect(agent({"action": "decide", **bound, "decision": "approve"}), ok=False, code="AGENT_CANNOT_DECIDE")
            expect(agent({"action": "inspect", **bound, "uid": owner_sid}), ok=False, code="UNEXPECTED_FIELDS")
            checks.append("agent_cannot_approve_or_claim_owner")
            expect(agent({"action": "decide", **bound, "decision": "approve"}, private=True),
                   ok=False, winerror=5)
            checks.append("private_pipe_acl_denies_agent")
            expect(agent({"action": "inspect", **bound}, expected_pid=os.getpid() + 1),
                   ok=False, code="WRONG_SERVER_PROCESS")
            checks.append("client_rejects_wrong_server_pid")
            wrong = {**bound, "operation_sha256": "0" * 64}
            expect(owner({"action": "decide", **wrong, "decision": "approve"}), ok=False, code="OPERATION_CHANGED")
            inspected = expect(owner({"action": "inspect", **bound}), ok=True, state="pending")
            if inspected["operation"] != operation:
                raise AssertionError("IMMUTABLE_OPERATION_CHANGED")
            expect(owner({"action": "decide", **bound, "decision": "approve"}), ok=True, state="approved")
            expect(agent({"action": "consume", **wrong}), ok=False, code="OPERATION_CHANGED")
            expect(agent({"action": "consume", **bound}), ok=True, state="consumed")
            expect(agent({"action": "consume", **bound}), ok=False, code="APPROVAL_REQUIRED")
            checks.extend(["owner_reviews_exact_operation", "changed_digest_refused", "single_consumption_replay_refused"])
            second = expect(agent({"action": "propose", "operation": operation}), ok=True, state="pending")
            second_bound = {key: second[key] for key in bound}
            expect(owner({"action": "decide", **second_bound, "decision": "reject"}), ok=True, state="rejected")
            expect(agent({"action": "consume", **second_bound}), ok=False, code="APPROVAL_REQUIRED")
            checks.append("owner_reject_blocks_consumption")
            # Same Ledger, fresh process-lifetime instance: no persisted approval recovery.
            old_instance = server.ledger.instance
            server.ledger.close()
            server.ledger = core.Ledger(owner_sid, [account.sid], policy, host)
            if old_instance == server.ledger.instance:
                raise AssertionError("OWNER_EPOCH_REUSED")
            expect(agent({"action": "consume", **bound}), ok=False, code="UNKNOWN_REQUEST")
            checks.append("fresh_ledger_does_not_restore_old_approval")
            if server.errors:
                raise AssertionError("SERVER_THREAD_FAILED")
        finally:
            shutil.rmtree(root)
    return {"schema": "yc59-windows-owner-boundary/v1", "result": "WINDOWS_ACCOUNT_BOUNDARY_OBSERVED",
            "peer_identity_source": "ImpersonateNamedPipeClient/TokenUser",
            "approval_origin": "automated_owner_account_fixture", "checks": checks,
            "human_consent_proven": False, "yc_authorization_binding_proven": False,
            "installed_host_proven": False, "deployment_authorized": False,
            "cloud_invocations": 0, "operation_executions": 0, "temporary_account_removed": True}


def client(request_path, output):
    import pipe_transport as pipe
    request = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        value = pipe.call(request["address"], request["request"], request["pid"])
    except OSError as error:
        value = {"ok": False, "winerror": error.winerror}
    except ValueError as error:
        value = {"ok": False, "code": str(error)}
    output.write_text(json.dumps({**value, "client_sid": pipe.current_sid()}), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--owner-core", type=Path, required=True)
    child = sub.add_parser("client")
    child.add_argument("--request", type=Path, required=True)
    child.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "client":
        client(args.request, args.output)
    else:
        print(json.dumps(run_probe(args.owner_core), indent=2))


if __name__ == "__main__":
    main()

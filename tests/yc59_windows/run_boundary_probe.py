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
import time
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
            # The copied client imports the token observer from a minimal tools tree.
            # Agent receives read-only source, never owner state or credentials.
            shutil.copyfile(Path(__file__).resolve().parents[2] / "tools/windows_owner_boundary.py",
                            root / "windows_owner_boundary.py")
            shutil.copyfile(Path(__file__).resolve().parents[2] / "tools/windows_owner_pipe.py",
                            root / "windows_owner_pipe.py")
            exchange = root / "exchange"
            exchange.mkdir()
            subprocess.run(["icacls.exe", str(exchange), "/grant:r", f"*{account.sid}:(OI)(CI)M"],
                           check=True, capture_output=True)
            policy, host = "synthetic-owner-policy/v1", str(uuid.uuid4())
            server = pipe.Server(core, owner_sid, account.sid, policy, host, "yc59-" + uuid.uuid4().hex,
                                 require_separate_sessions=False)
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
            server = pipe.Server(core, owner_sid, account.sid, policy, host, "yc59-strict-" + uuid.uuid4().hex)
            refused = agent({"action": "propose", "operation": operation})
            if (refused.get("ok") is not False or refused.get("code") not in
                    {"SEPARATE_WINDOWS_SESSIONS_REQUIRED", "INTERACTIVE_WINDOWS_SESSIONS_REQUIRED"}):
                raise AssertionError("SAME_SESSION_MUST_NOT_ADMIT_OWNER_UI")
            if server.ledger.entries:
                raise AssertionError("SAME_SESSION_CREATED_APPROVAL")
            checks.append("strict_profile_refuses_same_or_noninteractive_windows_session")

            # Real Windows SID/DACL, existing owner, typed YC intent, synthetic backend.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
            from yc_snapshot_read import ReadContext, ReadError, ReadProfile, dispatch_read
            from yc_read_projection import SnapshotSelection
            from dataclasses import replace
            selection = SnapshotSelection("synthetic-folder", "synthetic-vm", "synthetic-disk", "synthetic-snapshot")
            ctx = ReadContext(selection, "synthetic-cloud", str(uuid.uuid4()), time.monotonic(),
                str(uuid.uuid4()), str(uuid.uuid4()), host, "a" * 64, str(root / "nonexistent-yc-fixture.exe"),
                "synthetic-file-identity", "b" * 64, "synthetic-not-installed", str(root),
                "synthetic-environment", str(uuid.uuid4()), "windows")
            native, starts = ["ask"], []
            profile = ReadProfile(lambda: ctx, lambda _: native[0])
            payloads = {
                "instance": {"id": selection.vm_id, "folderId": selection.folder_id,
                    "bootDisk": {"diskId": selection.disk_id}, "metadata": {"user-data": "PRIVATE_SENTINEL"}},
                "disk": {"id": selection.disk_id, "folderId": selection.folder_id, "instanceIds": [selection.vm_id],
                    "status": "READY", "size": "1024", "typeId": "network-ssd", "zoneId": "ru-central1-a"},
                "snapshot": {"id": selection.snapshot_id, "folderId": selection.folder_id,
                    "sourceDiskId": selection.disk_id, "status": "READY", "diskSize": "1024",
                    "createdAt": "2026-11-01T10:00:00Z", "description": "PRIVATE_SENTINEL"}}

            def start_fixture(execution, argv):
                if list(argv) not in profile.operation()["execution"]["argv"]:
                    raise AssertionError("FIXTURE_ARGV_CHANGED")
                starts.append(argv)
                # This is explicitly NOT a YC binary invocation. Only synthetic JSON.
                code = "import sys;sys.stdout.write(" + repr(json.dumps(payloads[argv[2]])) + ")"
                return subprocess.Popen([sys.executable, "-I", "-c", code], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)

            def consume_read(ledger, sid, request):
                try:
                    return dispatch_read(ledger, sid, request, profile=profile, start=start_fixture)
                except ReadError as error:
                    raise core.Refusal(error.code) from None

            server = pipe.Server(core, owner_sid, account.sid, ctx.policy_revision, host,
                "yc59-read-" + uuid.uuid4().hex, canonicalizer=profile.canonicalize,
                consume_check=profile.check_consumption, consume_handler=consume_read,
                require_separate_sessions=False)
            proposal = expect(agent({"action": "propose", "operation": profile.operation()}), ok=True, state="pending")
            bound = {k: proposal[k] for k in ("request_id", "operation_sha256")}
            expect(agent({"action": "consume", **bound}), ok=False, code="APPROVAL_REQUIRED")
            expect(agent({"action": "decide", **bound, "decision": "approve"}), ok=False, code="AGENT_CANNOT_DECIDE")
            expect(agent({"action": "decide", **bound, "decision": "approve"}, private=True), ok=False, winerror=5)
            if starts:
                raise AssertionError("READ_BEFORE_APPROVAL")
            reviewed = expect(owner({"action": "inspect", **bound}), ok=True)
            if reviewed["operation"] != profile.operation():
                raise AssertionError("YC_REVIEW_BINDING_CHANGED")
            expect(owner({"action": "decide", **bound, "decision": "approve"}), ok=True, state="approved")
            completed = expect(agent({"action": "consume", **bound}), ok=True, state="consumed", logical_reads_completed=3)
            if len(starts) != 3 or "PRIVATE_SENTINEL" in json.dumps(completed):
                raise AssertionError("READ_COUNT_OR_PROJECTION_FAILED")
            expect(completed["projection"], snapshot_ready=True, restore_verified=False, independent_guard_readback=False)
            expect(agent({"action": "consume", **bound}), ok=False, code="APPROVAL_REQUIRED")
            if len(starts) != 3:
                raise AssertionError("REPLAY_STARTED_READ")
            checks.append("yc_profile_once_to_bounded_synthetic_projection")
            for drift in ("snapshot", "native_deny"):
                pending = expect(agent({"action": "propose", "operation": profile.operation()}), ok=True, state="pending")
                token = {k: pending[k] for k in bound}
                expect(owner({"action": "decide", **token, "decision": "approve"}), ok=True, state="approved")
                original = ctx
                if drift == "snapshot":
                    ctx = replace(ctx, selection=replace(selection, snapshot_id="synthetic-other"))
                else:
                    native[0] = "deny"
                expect(agent({"action": "consume", **token}), ok=False, code="CONSUME_CONTEXT_CHANGED")
                ctx, native[0] = original, "ask"
                expect(agent({"action": "consume", **token}), ok=False, code="APPROVAL_REQUIRED")
                if len(starts) != 3:
                    raise AssertionError("DRIFT_STARTED_READ")
            checks.append("yc_target_drift_and_native_deny_revoke_before_start")
            if server.errors:
                raise AssertionError("YC_SERVER_THREAD_FAILED")
            # Reuse this SAME disposable CI account. No new installed-host probe.
            import windows_owner_pipe as bounded
            received = []
            def echo(channel, principal, raw):
                received.append((channel, principal.sid))
                return b'{"ok":true}'
            with bounded.Transport("yc59-bounded-" + uuid.uuid4().hex, account.sid, echo) as transport:
                request_path = exchange / "bounded-request.json"
                result_path = exchange / "bounded-result.json"
                request_path.write_text(json.dumps({"address": transport.addresses["agent"], "pid": os.getpid(),
                    "owner": {"sid": transport.owner.sid, "session_id": transport.owner.session_id}}), encoding="utf-8")
                account.run([sys.executable, str(root / "run_boundary_probe.py"), "client-bounded",
                             "--request", str(request_path), "--output", str(result_path)], exchange)
                expect(json.loads(result_path.read_text(encoding="utf-8")), ok=True,
                       token_duplicate_denied=True, process_write_denied=True)
                if received != [("agent", account.sid)]:
                    raise AssertionError("BOUNDED_PEER_SID_MISMATCH")
            checks.append("bounded_transport_cross_account_server_token_query_without_write_or_duplicate")
        finally:
            shutil.rmtree(root)
    return {"schema": "yc59-windows-owner-boundary/v2", "result": "WINDOWS_ACCOUNT_AND_SYNTHETIC_READ_BOUNDARY_OBSERVED",
            "peer_identity_source": "ImpersonateNamedPipeClient/TokenUser",
            "approval_origin": "automated_owner_account_fixture", "checks": checks,
            "human_consent_proven": False, "yc_authorization_binding_proven": False,
            "installed_host_proven": False, "deployment_authorized": False,
            "cloud_invocations": 0, "operation_executions": 0, "synthetic_child_processes": len(starts),
            "yc_profile_binding_synthetic_proven": True, "temporary_account_removed": True,
            "positive_scope": "same_windows_session_transport_fixture_only",
            "separate_interactive_sessions_proven": False}


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


def client_bounded(request_path, output):
    import windows_owner_pipe as bounded
    import windows_owner_boundary as boundary
    request = json.loads(request_path.read_text(encoding="utf-8"))
    k = bounded.Kernel()
    value = json.loads(bounded.call(request["address"], b"synthetic", expected_pid=request["pid"],
                                   expected_owner=boundary.Principal(**request["owner"])))
    process = k.open_process(0x1000, False, request["pid"])
    if not process:
        raise AssertionError("SERVER_QUERY_GRANT_MISSING")
    token = W.HANDLE()
    try:
        # TOKEN_DUPLICATE must not be introduced by the read-only identity grant.
        allowed = k.open_process_token(process, 2, C.byref(token))
        value["token_duplicate_denied"] = not bool(allowed)
        if token:
            k.close(token)
    finally:
        k.close(process)
    writable = k.open_process(0x20, False, request["pid"])  # PROCESS_VM_WRITE
    value["process_write_denied"] = not bool(writable)
    if writable:
        k.close(writable)
    output.write_text(json.dumps(value), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--owner-core", type=Path, required=True)
    child = sub.add_parser("client")
    child.add_argument("--request", type=Path, required=True)
    child.add_argument("--output", type=Path, required=True)
    bounded_child = sub.add_parser("client-bounded")
    bounded_child.add_argument("--request", type=Path, required=True)
    bounded_child.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "client":
        client(args.request, args.output)
    elif args.mode == "client-bounded":
        client_bounded(args.request, args.output)
    else:
        print(json.dumps(run_probe(args.owner_core), indent=2))


if __name__ == "__main__":
    main()

"""Artificial facts and mock host events only; no command execution/real approvals."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from classifier_core import validate_result
from normalized_operation_identity import strict_loads
from prepared_process_adapter import (
    PROFILE, PreparedContractError, classify_prepared, encode_object_identity, project_prepared,
)
from prepared_process_authorization import AuthorizationError, CallBinding, create_local_session


# Shapes match agent-safe#33@2d29db8f core.rollback; this is a contract fixture,
# not a claim of running agent-safe or an authenticated OpenCode host.
@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    path: str
    size_bytes: int
    sha256: str
    object_identity: tuple[int, ...]


@dataclass(frozen=True)
class Prepared:
    source_txn_id: str
    attempt_txn_id: str
    role: str
    manifest_sha256: str
    program: str
    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: int
    stdin_utf8: str | None
    program_identity: tuple[int, ...]
    cwd_identity: tuple[int, ...]
    artifacts: tuple[Artifact, ...]


NS = 1790000000000000001
FILE = (1, 9007199254740993, 0o100600, 3, NS, NS + 1, 0, 0)
DIRECTORY = (1, 2, 0o40700, 0, 0)
SOURCE, ATTEMPT = "20260919-120000-1234abcd", "20260919-120001-5678abcd"


def prepared(platform="linux"):
    root = r"C:\work" if platform == "windows" else "/work"
    separator = "\\" if platform == "windows" else "/"
    script = root + separator + "restore"
    artifact = Artifact("restore", script, 3, hashlib.sha256(b"abc").hexdigest(), FILE)
    program = root + separator + ("python.exe" if platform == "windows" else "python")
    return Prepared(SOURCE, ATTEMPT, "process", "a" * 64, program,
        ("-I", script, "", "two words", "ёж", "$LITERAL", 'a"b', "line1\nline2"),
        root, 30, "a\r\nb\nc\rёж", FILE, DIRECTORY, (artifact,))


class ProjectionTests(unittest.TestCase):
    def test_exact_argv_stdin_and_safe_integer_encoding(self):
        for platform in ("linux", "windows"):
            with self.subTest(platform=platform):
                p = prepared(platform)
                projection = project_prepared(p, platform=platform)
                operation = projection.operation()
                self.assertEqual(operation["execution"]["argv"], [p.program, *p.argv])
                raw = p.stdin_utf8.encode("utf-8")
                self.assertEqual(operation["execution"]["stdin"], {"mode": "pipe", "encoding": "utf-8",
                    "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
                identity = operation["execution"]["executable"]["object_identity"]
                decoded = strict_loads(identity.split(":", 1)[1])
                self.assertEqual(decoded["components"]["mtime_ns"], str(NS))
                self.assertEqual(decoded["components"]["ino"], "9007199254740993")
                self.assertEqual(validate_result(classify_prepared(projection))["decision"], "ASK_USER")

    def test_devnull_empty_pipe_lf_crlf_are_distinct(self):
        ids = {project_prepared(replace(prepared(), stdin_utf8=value), platform="linux").operation_identity
               for value in (None, "", "\n", "\r\n", "ёж")}
        self.assertEqual(len(ids), 5)

    def test_every_stat_component_is_lossless_and_bound(self):
        original = encode_object_identity(FILE, kind="file", platform="linux")
        for index in range(len(FILE)):
            changed = list(FILE)
            changed[index] += 1
            if index == 7:  # unsupported reparse tag must reject, not normalize away
                with self.assertRaises(PreparedContractError):
                    encode_object_identity(tuple(changed), kind="file", platform="linux")
            else:
                self.assertNotEqual(encode_object_identity(tuple(changed), kind="file", platform="linux"), original)

    def test_execution_changes_identity(self):
        p = prepared()
        artifact = p.artifacts[0]
        original = project_prepared(p, platform="linux").operation_identity
        mutations = [replace(p, argv=(*p.argv, "")), replace(p, argv=(p.argv[0], p.argv[1], *reversed(p.argv[2:]))),
            replace(p, cwd="/other"), replace(p, program="/other/python"), replace(p, timeout_seconds=31),
            replace(p, cwd_identity=(1, 3, *DIRECTORY[2:])),
            replace(p, artifacts=(replace(artifact, sha256="b" * 64),)),
            replace(p, artifacts=(replace(artifact, object_identity=(2, *FILE[1:])),)),
            replace(p, artifacts=(replace(artifact, artifact_id="different"),))]
        for value in mutations:
            self.assertNotEqual(project_prepared(value, platform="linux").operation_identity, original)

    def test_roles_and_transactions_bound_separately_from_operation(self):
        p = prepared()
        original = project_prepared(p, platform="linux")
        for value in (replace(p, role="verify"), replace(p, attempt_txn_id="20260919-120002-abcdefab"),
                      replace(p, source_txn_id="20260919-120003-abcdefab"), replace(p, manifest_sha256="c" * 64)):
            projection = project_prepared(value, platform="linux")
            self.assertEqual(original.operation_identity, projection.operation_identity)
            self.assertNotEqual(original.snapshot_identity, projection.snapshot_identity)

    def test_artifact_order_semantic_set(self):
        p = prepared()
        second = replace(p.artifacts[0], artifact_id="backup", path="/work/backup")
        self.assertEqual(project_prepared(replace(p, artifacts=(*p.artifacts, second)), platform="linux"),
                         project_prepared(replace(p, artifacts=(second, *p.artifacts)), platform="linux"))

    def test_invalid_fields_and_profiles_fail_closed(self):
        p = prepared()
        bad = [replace(p, argv=list(p.argv)), replace(p, argv=("-c", "print(1)")),
            replace(p, argv=("-I", "/not/saved")), replace(p, timeout_seconds=True),
            replace(p, stdin_utf8="x" * 65537), replace(p, stdin_utf8="\ud800"),
            replace(p, program="relative"), replace(p, cwd="/work/../other"),
            replace(p, role="mutation"), replace(p, artifacts=(*p.artifacts, *p.artifacts)),
            replace(p, artifacts=(replace(p.artifacts[0], size_bytes=4),)),
            replace(p, program_identity=(True, *FILE[1:]))]
        for value in bad:
            with self.subTest(value=type(value).__name__), self.assertRaises(PreparedContractError):
                project_prepared(value, platform="linux")
        for kwargs in ({"platform": "darwin"}, {"platform": "linux", "profile": "v2"}):
            with self.assertRaises(PreparedContractError):
                project_prepared(p, **kwargs)
        with self.assertRaises(PreparedContractError):
            project_prepared(vars(p), platform="linux")
        @dataclass(frozen=True)
        class Extra(Prepared):
            approved: bool = True
        with self.assertRaises(PreparedContractError):
            project_prepared(Extra(**vars(p)), platform="linux")

    def test_windows_network_ads_and_batch_profile_rejected(self):
        p = prepared("windows")
        for path in (r"\\server\share\python.exe", r"C:\work\python.exe:stream", r"C:\work\wrapper.bat"):
            with self.assertRaises(PreparedContractError):
                project_prepared(replace(p, program=path), platform="windows")
        with self.assertRaises(PreparedContractError):
            project_prepared(replace(p, argv=("/c", "payload")), platform="windows")

    def test_native_deny_and_unknown_never_automatic_allow(self):
        projection = project_prepared(prepared(), platform="linux")
        for native, expected in (("deny", "DENY"), ("ask", "ASK_USER"), ("allow", "ASK_USER")):
            self.assertEqual(classify_prepared(projection, native_decision=native)["decision"], expected)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.current = prepared()
        self.native = "ask"
        self.now = 10.0
        self.host, self.consumer = create_local_session(session_id="session", platform="linux",
            acquire=lambda binding: replace(self.current, role=binding.role),
            native_check=lambda binding, projection: self.native, clock=lambda: self.now, ttl_seconds=30)
        self.binding = CallBinding("session", "call", SOURCE, ATTEMPT, "process")

    def pending(self, binding=None):
        return self.consumer.request(binding or self.binding)

    def approve(self, request, binding=None):
        self.host.approve_once(request.continuation, binding or self.binding,
                               snapshot_identity=request.projection.snapshot_identity)

    def assert_error(self, code, callback):
        with self.assertRaises(AuthorizationError) as cm:
            callback()
        self.assertEqual(cm.exception.code, code)

    def test_pending_cannot_execute_then_once_then_replay(self):
        p = self.pending()
        self.assertEqual(p.decision, "ASK_USER")
        self.assert_error("CONTINUATION_NOT_APPROVED", lambda: self.consumer.consume(p.continuation, self.binding))
        self.approve(p)
        self.assertEqual(self.consumer.consume(p.continuation, self.binding), p.projection)
        self.assert_error("CONTINUATION_CONSUMED", lambda: self.consumer.consume(p.continuation, self.binding))
        self.assert_error("CALL_ALREADY_REQUESTED", lambda: self.pending())

    def test_native_deny_no_continuation(self):
        self.native = "deny"
        p = self.pending()
        self.assertEqual(p.decision, "DENY")
        self.assertIsNone(p.continuation)
        self.assert_error("CONTINUATION_UNKNOWN", lambda: self.approve(p))

    def test_native_allow_still_needs_once_for_unknown_code(self):
        self.native = "allow"
        p = self.pending()
        self.assertEqual(p.decision, "ASK_USER")
        self.assert_error("CONTINUATION_NOT_APPROVED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_new_native_deny_revokes_previously_approved(self):
        p = self.pending()
        self.approve(p)
        self.native = "deny"
        self.assert_error("NATIVE_DENY", lambda: self.consumer.consume(p.continuation, self.binding))
        self.native = "ask"
        self.assert_error("CONTINUATION_REVOKED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_exact_binding_all_fields(self):
        for field, value in (("session_id", "other"), ("call_id", "other"), ("source_txn_id", "other"),
                             ("attempt_txn_id", "other"), ("role", "verify"), ("transport", "json")):
            self.setUp()
            p = self.pending()
            self.approve(p)
            self.assert_error("CALL_BINDING_MISMATCH",
                lambda: self.consumer.consume(p.continuation, replace(self.binding, **{field: value})))
            self.assert_error("CONTINUATION_REVOKED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_wrong_snapshot_not_approved(self):
        p = self.pending()
        self.assert_error("APPROVAL_SNAPSHOT_MISMATCH", lambda: self.host.approve_once(
            p.continuation, self.binding, snapshot_identity="sha256:" + "0" * 64))

    def test_each_role_has_independent_approval(self):
        process = self.pending()
        verify_binding = replace(self.binding, role="verify", call_id="verify-call")
        verify = self.pending(verify_binding)
        self.approve(process)
        self.consumer.consume(process.continuation, self.binding)
        self.assert_error("CONTINUATION_NOT_APPROVED", lambda: self.consumer.consume(verify.continuation, verify_binding))
        self.approve(verify, verify_binding)
        self.consumer.consume(verify.continuation, verify_binding)

    def test_expiry_pending_and_approved(self):
        for approved in (False, True):
            self.setUp()
            p = self.pending()
            if approved:
                self.approve(p)
            self.now = 40.0
            self.assert_error("CONTINUATION_EXPIRED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_provider_delay_cannot_outlive_expiry(self):
        p = self.pending()
        self.approve(p)
        def slow(binding, projection):
            self.now = 41.0
            return "ask"
        self.host._session.native_check = slow  # trusted mock composition root only
        self.assert_error("CONTINUATION_EXPIRED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_drift_burns_grant(self):
        p = self.pending()
        self.approve(p)
        original = self.current
        self.current = replace(original, stdin_utf8="changed")
        self.assert_error("PREPARED_DRIFT", lambda: self.consumer.consume(p.continuation, self.binding))
        self.current = original
        self.assert_error("CONTINUATION_REVOKED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_provider_failure_never_executes_and_does_not_leak(self):
        p = self.pending()
        self.approve(p)
        def failed(binding):
            raise ValueError("synthetic-private-input")
        self.host._session.acquire = failed
        self.assert_error("ACQUISITION_OR_POLICY_FAILED", lambda: self.consumer.consume(p.continuation, self.binding))

    def test_forged_boolean_dictionary_or_other_session_ticket_rejected(self):
        p = self.pending()
        for fake in (True, {"approved": True}, "ALLOW", object()):
            self.assert_error("CONTINUATION_UNKNOWN", lambda: self.consumer.consume(fake, self.binding))
        _, other = create_local_session(session_id="session", platform="linux", acquire=lambda b: self.current,
            native_check=lambda b, p: "ask")
        self.approve(p)
        self.assert_error("CONTINUATION_UNKNOWN", lambda: other.consume(p.continuation, self.binding))

    def test_cancel_and_close(self):
        p = self.pending()
        self.host.cancel(p.continuation)
        self.assert_error("CONTINUATION_REVOKED", lambda: self.approve(p))
        self.host.close()
        self.assert_error("SESSION_CLOSED", lambda: self.pending(replace(self.binding, call_id="new")))

    def test_concurrent_consumption_only_one_success(self):
        p = self.pending()
        self.approve(p)
        def consume(_):
            try:
                self.consumer.consume(p.continuation, self.binding)
                return "consumed"
            except AuthorizationError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(consume, range(8)))
        self.assertEqual(results.count("consumed"), 1)
        self.assertEqual(results.count("CONTINUATION_CONSUMED"), 7)

    def test_capacity_does_not_evict_replay_protection(self):
        host, consumer = create_local_session(session_id="session", platform="linux", acquire=lambda b: self.current,
            native_check=lambda b, p: "ask", capacity=1)
        consumer.request(self.binding)
        self.assert_error("SESSION_CAPACITY", lambda: consumer.request(replace(self.binding, call_id="new")))


if __name__ == "__main__":
    unittest.main()

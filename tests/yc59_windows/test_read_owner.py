"""Existing pinned Ledger + YC profile; temporary Python JSON children only.

Run explicitly with --owner-core; no silent skip when the required core is absent.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_yc_snapshot_read import PRIVATE, child, context, responses
from run_boundary_probe import load_core
from yc_read_projection import ProjectionError
from yc_snapshot_read import ReadError, ReadProfile, dispatch_read

CORE = None


class ReadOwnerTests(unittest.TestCase):
    def setUp(self):
        self.ctx, self.native, self.starts = context(), "ask", []
        self.profile = ReadProfile(lambda: self.ctx, lambda _: self.native)
        self.ledger = CORE.Ledger("owner", ["agent"], self.ctx.policy_revision, self.ctx.execution_host_id,
                                 canonicalizer=self.profile.canonicalize, consume_check=self.profile.check_consumption)
        self.payloads = responses()
        self.pending = self.ledger.handle("agent", "agent", {"action": "propose", "operation": self.profile.operation()})
        self.bound = {k: self.pending[k] for k in ("request_id", "operation_sha256")}

    def approve(self):
        return self.ledger.handle("decision", "owner", {"action": "decide", **self.bound, "decision": "approve"})

    def start(self, execution, argv):
        self.assertEqual(execution, self.profile.operation()["execution"])
        index = ["instance", "disk", "snapshot"].index(argv[2])
        self.assertEqual(list(argv), self.profile.operation()["execution"]["argv"][index])
        self.starts.append(argv)
        return child("import sys;sys.stderr.write(" + repr(PRIVATE) + ");sys.stdout.write(" + repr(json.dumps(self.payloads[index])) + ")")

    def dispatch(self, **updates):
        return dispatch_read(self.ledger, "agent", {"action": "consume", **self.bound, **updates},
                             profile=self.profile, start=self.start)

    def test_pending_self_approval_and_forged_flags_never_start_child(self):
        with self.assertRaisesRegex(CORE.Refusal, "APPROVAL_REQUIRED"):
            self.dispatch()
        with self.assertRaisesRegex(CORE.Refusal, "AGENT_CANNOT_DECIDE"):
            self.ledger.handle("agent", "agent", {"action": "decide", **self.bound, "decision": "approve"})
        self.approve()
        with self.assertRaisesRegex(CORE.Refusal, "UNEXPECTED_FIELDS"):
            self.dispatch(approved=True)
        self.assertEqual(self.starts, [])

    def test_approved_once_returns_only_projection_and_replay_does_not_spawn(self):
        self.approve()
        result = self.dispatch()
        self.assertEqual(len(self.starts), 3)
        self.assertTrue(result["projection"]["snapshot_ready"])
        self.assertFalse(result["projection"]["independent_guard_readback"])
        self.assertNotIn(PRIVATE, json.dumps(result))
        with self.assertRaisesRegex(CORE.Refusal, "APPROVAL_REQUIRED"):
            self.dispatch()
        self.assertEqual(len(self.starts), 3)

    def test_policy_credentials_binary_and_target_drift_revoke_before_spawn(self):
        original = self.ctx
        for change in ({"policy_revision": "c" * 64}, {"credential_context_id": original.call_id},
                       {"executable_sha256": "c" * 64},
                       {"selection": replace(original.selection, snapshot_id="synthetic-other")}):
            with self.subTest(change=list(change)):
                self.setUp()
                self.approve()
                self.ctx = replace(self.ctx, **change)
                with self.assertRaisesRegex(CORE.Refusal, "CONSUME_CONTEXT_CHANGED"):
                    self.dispatch()
                self.ctx = original
                with self.assertRaisesRegex(CORE.Refusal, "APPROVAL_REQUIRED"):
                    self.dispatch()
                self.assertEqual(self.starts, [])

    def test_native_deny_and_expiry_block_previously_approved_read(self):
        self.approve()
        self.native = "deny"
        with self.assertRaisesRegex(CORE.Refusal, "CONSUME_CONTEXT_CHANGED"):
            self.dispatch()
        self.assertEqual(self.starts, [])
        self.setUp()
        self.approve()
        deadline = self.ledger.entries[self.bound["request_id"]]["deadline"]
        self.ledger.clock = lambda: deadline + 1
        with self.assertRaisesRegex(CORE.Refusal, "REQUEST_EXPIRED"):
            self.dispatch()
        self.assertEqual(self.starts, [])

    def test_mismatched_snapshot_returns_no_partial_projection_or_new_grant(self):
        self.approve()
        self.payloads[2]["sourceDiskId"] = "synthetic-other"
        with self.assertRaises(ProjectionError) as caught:
            self.dispatch()
        self.assertNotIn(PRIVATE, str(caught.exception))
        with self.assertRaisesRegex(CORE.Refusal, "APPROVAL_REQUIRED"):
            self.dispatch()
        self.assertEqual(len(self.starts), 3)

    def test_failed_spawn_burns_grant_without_automatic_retry(self):
        self.approve()
        def broken(*_):
            self.starts.append("attempt")
            raise ValueError(PRIVATE)
        with self.assertRaisesRegex(ReadError, "YC_READ_START_FAILED") as caught:
            dispatch_read(self.ledger, "agent", {"action": "consume", **self.bound}, profile=self.profile, start=broken)
        self.assertNotIn(PRIVATE, str(caught.exception))
        with self.assertRaises(CORE.Refusal):
            self.dispatch()
        self.assertEqual(self.starts, ["attempt"])

    def test_context_change_between_steps_stops_before_next_child(self):
        self.approve()
        def changing(execution, argv):
            process = self.start(execution, argv)
            self.ctx = replace(self.ctx, executable_identity="changed-file")
            return process
        with self.assertRaises(ReadError):
            dispatch_read(self.ledger, "agent", {"action": "consume", **self.bound}, profile=self.profile, start=changing)
        self.assertEqual(len(self.starts), 1)

    def test_concurrent_consume_starts_only_one_three_read_sequence(self):
        self.approve()
        def run(_):
            try:
                return self.dispatch()["logical_reads_completed"]
            except CORE.Refusal:
                return 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            counts = list(pool.map(run, range(8)))
        self.assertEqual(counts.count(3), 1)
        self.assertEqual(counts.count(0), 7)
        self.assertEqual(len(self.starts), 3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-core", type=Path, required=True)
    args = parser.parse_args()
    CORE = load_core(args.owner_core)
    unittest.main(argv=[sys.argv[0]], verbosity=2)

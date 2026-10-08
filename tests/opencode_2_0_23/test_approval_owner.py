"""Проверки автомата разрешений. Kernel/реальный OpenCode проверяются отдельно."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import unittest

from approval_owner import Ledger, Refusal, canonical, strict_json


def operation(action="sudo_job.start"):
    command = "synthetic-no-execution"
    return {"schema": 1, "action": action,
            "job_id": "11111111-1111-4111-8111-111111111111",
            "transaction_id": "22222222-2222-4222-8222-222222222222",
            "execution_host_id": "33333333-3333-4333-8333-333333333333",
            "command": command, "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
            "argv": ["/synthetic/relay", "sudo-job", "start", command],
            "executable": "/synthetic/relay", "cwd": "/synthetic/project", "policy_revision": "fixture-policy-v1",
            "ssh_identity": {"remote_host": "example.invalid", "remote_port": 22, "remote_user": "fixture",
                             "host_key_algorithm": "ssh-ed25519", "remote_host_key_sha256": "SHA256:" + "A" * 43,
                             "daemon_instance_id": "44444444-4444-4444-8444-444444444444", "connection_generation": 1}}


class ApprovalOwnerTests(unittest.TestCase):
    def setUp(self):
        self.time = [10]
        self.ledger = Ledger(1, [2, 3], "fixture-policy-v1", operation()["execution_host_id"],
                             ttl=10, clock=lambda: self.time[0])
        self.op = operation()
        self.request = self.ledger.handle("agent", 2, {"action": "propose", "operation": self.op})

    def call(self, action, *, channel="agent", uid=2, **updates):
        request = {"action": action, "request_id": self.request["request_id"],
                   "operation_sha256": self.request["operation_sha256"], **updates}
        return self.ledger.handle(channel, uid, request)

    def approve(self):
        return self.call("decide", channel="decision", uid=1, decision="approve")

    def test_agent_cannot_decide_or_fake_uid(self):
        for fields in ({"decision": "approve"}, {"decision": "approve", "uid": 1}, {"approved": True}):
            with self.subTest(fields=fields), self.assertRaises(Refusal):
                self.call("decide", **fields)
        with self.assertRaisesRegex(Refusal, "NOT_DECISION_OWNER"):
            self.call("decide", channel="decision", decision="approve")
        self.assertEqual(self.call("inspect")["state"], "pending")

    def test_pending_cannot_be_consumed(self):
        with self.assertRaisesRegex(Refusal, "APPROVAL_REQUIRED"):
            self.call("consume")

    def test_immutable_review_after_caller_mutation(self):
        original = copy.deepcopy(self.op)
        self.op["command"] = "different-command"
        self.op["ssh_identity"]["connection_generation"] = 9
        reviewed = self.call("inspect", channel="decision", uid=1)
        self.assertEqual(reviewed["operation"], original)
        self.assertNotIn("operation", self.call("inspect"))

    def test_hash_change_rejected_for_all_bound_fields(self):
        for field, replacement in (("argv", ["/different/relay"]), ("cwd", "/other"),
                                   ("job_id", "55555555-5555-4555-8555-555555555555"),
                                   ("policy_revision", "v2"), ("action", "sudo_job.stop"),
                                   ("ssh_identity", {**self.op["ssh_identity"], "connection_generation": 2}),
                                   ("transaction_id", "66666666-6666-4666-8666-666666666666"),
                                   ("executable", "/different/relay"), ("command", "other-bytes")):
            changed = copy.deepcopy(self.op)
            changed[field] = replacement
            digest = hashlib.sha256(json.dumps(changed, sort_keys=True,
                                      ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            with self.subTest(field=field), self.assertRaisesRegex(Refusal, "OPERATION_CHANGED"):
                self.call("decide", channel="decision", uid=1, decision="approve", operation_sha256=digest)

    def test_once_replay_and_second_decision_rejected(self):
        self.approve()
        self.assertEqual(self.call("consume")["state"], "consumed")
        with self.assertRaisesRegex(Refusal, "APPROVAL_REQUIRED"):
            self.call("consume")
        with self.assertRaisesRegex(Refusal, "DECISION_ALREADY_FINAL"):
            self.approve()

    def test_concurrent_consume_only_one_wins(self):
        self.approve()
        def consume(_):
            try:
                return self.call("consume")["state"]
            except Refusal:
                return "refused"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(consume, range(16)))
        self.assertEqual(results.count("consumed"), 1)
        self.assertEqual(results.count("refused"), 15)

    def test_reject_cancel_and_expiry_block_late_approval(self):
        self.call("decide", channel="decision", uid=1, decision="reject")
        with self.assertRaises(Refusal):
            self.approve()
        self.request = self.ledger.handle("agent", 2, {"action": "propose", "operation": self.op})
        self.call("cancel")
        with self.assertRaises(Refusal):
            self.approve()
        self.request = self.ledger.handle("agent", 2, {"action": "propose", "operation": self.op})
        self.time[0] = 21
        with self.assertRaisesRegex(Refusal, "REQUEST_EXPIRED"):
            self.approve()

    def test_close_and_restart_do_not_restore_request(self):
        self.approve()
        self.ledger.close()
        with self.assertRaisesRegex(Refusal, "OWNER_CLOSED"):
            self.call("consume")
        self.ledger = Ledger(1, [2], "fixture-policy-v1", self.op["execution_host_id"])
        with self.assertRaisesRegex(Refusal, "UNKNOWN_REQUEST"):
            self.call("consume")

    def test_start_does_not_approve_stop(self):
        self.approve()
        start = self.request
        self.request = self.ledger.handle("agent", 2, {"action": "propose", "operation": operation("sudo_job.stop")})
        with self.assertRaisesRegex(Refusal, "APPROVAL_REQUIRED"):
            self.call("consume")
        self.assertNotEqual(start["operation_sha256"], self.request["operation_sha256"])

    def test_other_uid_cannot_consume(self):
        self.approve()
        with self.assertRaisesRegex(Refusal, "WRONG_CALLER"):
            self.call("consume", uid=3)

    def test_policy_host_and_deny_checked_before_pending(self):
        for field in ("policy_revision", "execution_host_id"):
            changed = copy.deepcopy(self.op)
            changed[field] = "55555555-5555-4555-8555-555555555555"
            with self.subTest(field=field), self.assertRaises(Refusal):
                self.ledger.handle("agent", 2, {"action": "propose", "operation": changed})
        denied = Ledger(1, [2], "fixture-policy-v1", self.op["execution_host_id"],
                        blocked_hashes=[self.op["command_sha256"]])
        with self.assertRaisesRegex(Refusal, "POLICY_DENY"):
            denied.handle("agent", 2, {"action": "propose", "operation": self.op})
        self.assertEqual(denied.entries, {})

    def test_json_and_unexpected_approval_fields_rejected(self):
        with self.assertRaises(Refusal):
            strict_json('{"action":"propose","action":"decide"}')
        with self.assertRaises(Refusal):
            strict_json('{"value":NaN}')
        self.op["approved"] = True
        with self.assertRaises(Refusal):
            canonical(self.op)


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
MODULE = ROOT / "authorization_broker" / "state_model.py"
spec = importlib.util.spec_from_file_location("broker_state_model", MODULE)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)

SOURCE = ("session-1", "message-1", "call-1")
OP_A = "sha256:operation-a"
OP_B = "sha256:operation-b"


class GateBBrokerStateModelTests(unittest.TestCase):
    def setUp(self):
        self.b = m.BrokerStateModel()

    def approve_a(self):
        aid = self.b.request("host-peer", OP_A, SOURCE, "ASK_USER")
        self.b.approve_once(aid)
        return aid

    def assert_code(self, code, fn):
        with self.assertRaises(m.BrokerContractError) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code)

    def test_a8_exact_grant_operation_consumes_once(self):
        aid = self.approve_a()
        self.assertEqual(
            self.b.consume("pep-peer", aid, OP_A, SOURCE),
            "ALLOW_EXECUTION_ONCE",
        )
        self.assertEqual(self.b.grants[aid].state, "CONSUMED")

    def test_a9_operation_substitution_rejected(self):
        aid = self.approve_a()
        self.assert_code(
            "OPERATION_IDENTITY_MISMATCH",
            lambda: self.b.consume("pep-peer", aid, OP_B, SOURCE),
        )
        self.assertEqual(self.b.grants[aid].state, "APPROVED")

    def test_a10_target_substitution_rejected_by_operation_identity(self):
        aid = self.approve_a()
        substituted_target_identity = "sha256:operation-a-target-substituted"
        self.assert_code(
            "OPERATION_IDENTITY_MISMATCH",
            lambda: self.b.consume("pep-peer", aid, substituted_target_identity, SOURCE),
        )

    def test_a11_replay_rejected(self):
        aid = self.approve_a()
        self.b.consume("pep-peer", aid, OP_A, SOURCE)
        self.assert_code(
            "GRANT_ALREADY_CONSUMED",
            lambda: self.b.consume("pep-peer", aid, OP_A, SOURCE),
        )

    def test_model_child_cannot_consume_known_authorization_id(self):
        aid = self.approve_a()
        self.assert_code(
            "UNTRUSTED_PEP",
            lambda: self.b.consume("model-child", aid, OP_A, SOURCE),
        )

    def test_model_child_cannot_create_trusted_request(self):
        self.assert_code(
            "UNTRUSTED_HOST",
            lambda: self.b.request("model-child", OP_A, SOURCE, "ASK_USER"),
        )

    def test_source_call_substitution_rejected(self):
        aid = self.approve_a()
        self.assert_code(
            "SOURCE_BINDING_MISMATCH",
            lambda: self.b.consume(
                "pep-peer", aid, OP_A, ("session-1", "message-1", "call-2")
            ),
        )

    def test_aborted_source_rejected(self):
        aid = self.approve_a()
        self.b.abort_source(SOURCE)
        self.assert_code(
            "SOURCE_NOT_ACTIVE",
            lambda: self.b.consume("pep-peer", aid, OP_A, SOURCE),
        )

    def test_host_exit_invalidates_consumption(self):
        aid = self.approve_a()
        self.b.host_exit()
        self.assert_code(
            "HOST_NOT_LIVE",
            lambda: self.b.consume("pep-peer", aid, OP_A, SOURCE),
        )

    def test_broker_restart_invalidates_old_grant(self):
        aid = self.approve_a()
        self.b.broker_restart()
        self.assert_code(
            "GRANT_NOT_FOUND",
            lambda: self.b.consume("pep-peer", aid, OP_A, SOURCE),
        )

    def test_hard_deny_creates_no_approvable_grant(self):
        self.assert_code(
            "HARD_DENY_NO_GRANT",
            lambda: self.b.request("host-peer", OP_A, SOURCE, "DENY"),
        )
        self.assertEqual(self.b.grants, {})


if __name__ == "__main__":
    unittest.main()

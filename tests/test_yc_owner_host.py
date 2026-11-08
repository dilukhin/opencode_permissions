"""Host protocol tests with synthetic tokens/context, never Windows deployment."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from runtime.approval_owner.read_host import ReadHost
from test_yc_snapshot_read import context
import windows_owner_boundary as boundary

OWNER = boundary.Principal("S-1-5-21-1", 2)
AGENT = boundary.Principal("S-1-5-21-2", 1)


class ReadHostProtocolTests(unittest.TestCase):
    def setUp(self):
        self.ctx, self.native, self.start = context(), "ask", Mock()
        with patch("runtime.approval_owner.read_host.boundary.current", return_value=OWNER), \
                patch("runtime.approval_owner.read_host.Transport"):
            self.host = ReadHost("fixture", AGENT.sid, current_context=lambda: self.ctx,
                                 native_check=lambda _: self.native, start=self.start)

    def tearDown(self):
        self.host.close()

    def request(self, channel, principal, request):
        return json.loads(self.host.handle(channel, principal, json.dumps(request).encode()))

    def propose(self, principal=AGENT):
        return self.request("agent", principal, {"action": "propose", "operation": self.host.profile.operation()})

    def test_admission_before_pending_is_always_strict(self):
        for principal in (OWNER, boundary.Principal(AGENT.sid, OWNER.session_id),
                          boundary.Principal(AGENT.sid, 0), boundary.Principal("S-1-5-21-3", 3)):
            self.assertFalse(self.propose(principal)["ok"])
        self.assertEqual(self.host.ledger.entries, {})
        self.start.assert_not_called()

    def test_malformed_request_id_does_not_stop_owner(self):
        for value in ([], {}, 1, None):
            self.assertEqual(self.request("agent", AGENT, {"action": "consume", "request_id": value,
                                                           "operation_sha256": "a" * 64})["code"], "UNKNOWN_REQUEST")
        self.assertFalse(self.host.ledger.closed)
        self.assertTrue(self.propose()["ok"])

    def test_describe_is_authenticated_unapproved_and_rejects_extra_fields(self):
        result = self.request("agent", AGENT, {"action": "describe"})
        self.assertTrue(result["ok"] and result["approval_required"])
        self.assertEqual(result["operation"], self.host.profile.operation())
        self.assertEqual(self.host.ledger.entries, {})
        for actor, request in ((OWNER, {"action": "describe"}),
                               (AGENT, {"action": "describe", "approved": True})):
            self.assertFalse(self.request("agent", actor, request)["ok"])
        self.start.assert_not_called()

    def test_pending_notification_carries_only_actual_ledger_binding(self):
        proposed = self.propose()
        self.assertEqual(self.host.pending.get_nowait(),
                         {k: proposed[k] for k in ("request_id", "operation_sha256")})
        self.start.assert_not_called()

    def test_completed_owner_record_matches_actual_projected_reply_once(self):
        from test_yc_snapshot_read import responses, child, PRIVATE
        payloads = responses()
        self.start.side_effect = lambda execution, argv: child(
            'import sys;sys.stdout.write(' + repr(json.dumps(payloads[['instance','disk','snapshot'].index(argv[2])])) + ')')
        proposed = self.propose()
        bound = {k: proposed[k] for k in ('request_id','operation_sha256')}
        self.request('decision', OWNER, {'action':'decide', **bound, 'decision':'approve'})
        result = self.request('agent', AGENT, {'action':'consume', **bound})
        self.assertTrue(result['ok'])
        self.assertEqual(result['logical_reads_completed'], 3)
        self.assertEqual(self.host.completed.get_nowait(), result)
        self.assertNotIn(PRIVATE, json.dumps(result))
        replay = self.request('agent', AGENT, {'action':'consume', **bound})
        self.assertFalse(replay['ok'])
        self.assertTrue(self.host.completed.empty())

    def test_owner_inspects_kernel_origin_and_agent_cannot_decide(self):
        proposed = self.propose()
        bound = {k: proposed[k] for k in ("request_id", "operation_sha256")}
        viewed = self.request("decision", OWNER, {"action": "inspect", **bound})
        self.assertTrue(viewed["session_separation_required"])
        self.assertEqual(viewed["request_origin"], {"sid": AGENT.sid, "session_id": AGENT.session_id})
        denied = self.request("agent", AGENT, {"action": "decide", **bound, "decision": "approve"})
        self.assertEqual(denied["code"], "AGENT_CANNOT_DECIDE")
        self.assertFalse(self.request("decision", AGENT, {"action": "decide", **bound, "decision": "approve"})["ok"])
        self.start.assert_not_called()

    def test_other_session_of_same_agent_sid_cannot_use_or_cancel_request(self):
        proposed = self.propose()
        bound = {k: proposed[k] for k in ("request_id", "operation_sha256")}
        other = boundary.Principal(AGENT.sid, 3)
        for action in ("inspect", "cancel", "consume"):
            self.assertEqual(self.request("agent", other, {"action": action, **bound})["code"], "WRONG_REQUEST_SESSION")
        self.assertEqual(self.host.ledger.entries[bound["request_id"]]["state"], "pending")

    def test_deny_drift_and_failed_spawn_never_restore_approval(self):
        proposed = self.propose()
        bound = {k: proposed[k] for k in ("request_id", "operation_sha256")}
        self.assertTrue(self.request("decision", OWNER, {"action": "decide", **bound, "decision": "approve"})["ok"])
        self.native = "deny"
        self.assertEqual(self.request("agent", AGENT, {"action": "consume", **bound})["code"], "CONSUME_CONTEXT_CHANGED")
        self.native = "ask"
        self.assertEqual(self.request("agent", AGENT, {"action": "consume", **bound})["code"], "APPROVAL_REQUIRED")
        self.start.assert_not_called()

    def test_unavailable_native_provider_does_not_construct_host_or_start_transport(self):
        with patch("runtime.approval_owner.read_host.boundary.current", return_value=OWNER), \
                patch("runtime.approval_owner.read_host.Transport") as transport:
            with self.assertRaises(Exception):
                ReadHost("fixture", AGENT.sid, current_context=lambda: self.ctx,
                         native_check=lambda _: "unknown", start=self.start)
            transport.assert_not_called()

    def test_strict_json_and_extra_approval_flag_never_start(self):
        for raw in (b'{"action":"propose","action":"consume"}', b'[]', b'NaN'):
            self.assertFalse(json.loads(self.host.handle("agent", AGENT, raw))["ok"])
        operation = self.host.profile.operation()
        self.assertEqual(self.request("agent", AGENT, {"action": "propose", "operation": operation, "approved": True})["code"], "UNEXPECTED_FIELDS")
        self.assertEqual(self.host.ledger.entries, {})
        self.start.assert_not_called()

    def test_shutdown_cancels_grants_and_starter(self):
        proposed = self.propose()
        self.host.close()
        self.assertEqual(self.host.ledger.entries[proposed["request_id"]]["state"], "cancelled")
        with self.assertRaises(Exception):
            self.host.start({}, ())
        self.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()

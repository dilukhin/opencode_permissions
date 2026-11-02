"""Portable negative checks; Windows account proof belongs to the dedicated CI job."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("yc59_windows_probe", ROOT / "tests/yc59_windows/run_boundary_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
review_spec = importlib.util.spec_from_file_location("yc59_owner_review", ROOT / "tests/yc59_windows/review_read_request.py")
review_ui = importlib.util.module_from_spec(review_spec)
review_spec.loader.exec_module(review_ui)
OWNER = review_ui.boundary.Principal("S-1-5-21-1", 2)
AGENT = "S-1-5-21-2"


def with_origin(value):
    return {**value, "owner_actor": {"sid": OWNER.sid, "session_id": OWNER.session_id},
            "request_origin": {"sid": AGENT, "session_id": 3}, "session_separation_required": True}


class WindowsFixtureGuards(unittest.TestCase):
    def test_refuses_installed_host_before_account_or_pipe_import(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "EPHEMERAL_GITHUB_HOSTED_WINDOWS_REQUIRED"):
                probe.run_probe(Path("unused-owner-core.py"))

    def test_changed_owner_dependency_rejected_before_python_import(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.py"
            marker = Path(directory) / "executed"
            source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OWNER_CORE_DIGEST_MISMATCH"):
                probe.load_core(source)
            self.assertFalse(marker.exists())

    def test_review_pipe_or_reject_never_approves_implicitly(self):
        from unittest.mock import Mock
        call = Mock()
        with self.assertRaisesRegex(ValueError, "OWNER_TERMINAL_REQUIRED"):
            review_ui.review(call, "11111111-1111-4111-8111-111111111111", "a" * 64, terminal=False)
        call.assert_not_called()
        inspected = {"ok": True, "state": "pending", "request_id": "11111111-1111-4111-8111-111111111111", "operation_sha256": "a" * 64,
                     "owner_instance_id": "instance", "operation": {"schema": "yc-snapshot-read/v1",
                     "action": "yc.snapshot.read", "scope": {"snapshot_id": "fixture\u001b[31m\u202e"}}}
        call.side_effect = [with_origin(inspected), {**inspected, "state": "rejected"}]
        displayed = []
        result = review_ui.review(call, "11111111-1111-4111-8111-111111111111", "a" * 64, terminal=True,
                                  owner_actor=OWNER, agent_sid=AGENT,
                                  read_line=lambda _: "", write_line=displayed.append)
        self.assertEqual(result, "reject")
        self.assertEqual(call.call_args.args[0]["decision"], "reject")
        self.assertNotIn("\u001b", "".join(displayed))
        self.assertNotIn("\u202e", "".join(displayed))

    def test_review_exact_explicit_choice_binds_same_request_and_owner_epoch(self):
        from unittest.mock import Mock
        viewed = {"ok": True, "state": "pending", "request_id": "11111111-1111-4111-8111-111111111111", "operation_sha256": "a" * 64,
                  "owner_instance_id": "instance", "operation": {"schema": "yc-snapshot-read/v1", "action": "yc.snapshot.read"}}
        call = Mock(side_effect=[with_origin(viewed), {**viewed, "state": "approved"}])
        self.assertEqual(review_ui.review(call, "11111111-1111-4111-8111-111111111111", "a" * 64, terminal=True,
            owner_actor=OWNER, agent_sid=AGENT,
            read_line=lambda _: "РАЗРЕШИТЬ ОДИН РАЗ 11111111-1111-4111-8111-111111111111", write_line=lambda _: None), "approve")
        self.assertEqual(call.call_args.args[0], {"action": "decide", "request_id": "11111111-1111-4111-8111-111111111111",
                                               "operation_sha256": "a" * 64, "decision": "approve"})

    def test_review_rejects_same_session_and_fixture_mode_before_reading_input(self):
        from unittest.mock import Mock
        viewed = with_origin({"ok": True, "state": "pending", "request_id": "11111111-1111-4111-8111-111111111111",
            "operation_sha256": "a" * 64, "owner_instance_id": "instance",
            "operation": {"schema": "yc-snapshot-read/v1", "action": "yc.snapshot.read"}})
        for changed in ({"request_origin": {"sid": AGENT, "session_id": 2}}, {"session_separation_required": False}):
            call, read_line = Mock(return_value={**viewed, **changed}), Mock()
            with self.assertRaises(ValueError):
                review_ui.review(call, viewed["request_id"], "a" * 64, terminal=True,
                                 owner_actor=OWNER, agent_sid=AGENT, read_line=read_line)
            self.assertEqual(call.call_count, 1)
            read_line.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from windows_owner_boundary import BoundaryError, Principal, admit
import yc_owner_actor_probe as probe


class OwnerBoundaryTests(unittest.TestCase):
    def test_different_sids_do_not_admit_same_interactive_windows_session(self):
        with self.assertRaisesRegex(BoundaryError, "SEPARATE_WINDOWS_SESSIONS_REQUIRED"):
            admit(Principal("S-1-5-21-1", 2), Principal("S-1-5-21-2", 2), "S-1-5-21-2")

    def test_sid_change_is_not_a_substitute_for_interactive_logon(self):
        for owner_session, agent_session in ((0, 1), (1, 0), (0, 0)):
            with self.subTest(owner_session=owner_session, agent_session=agent_session):
                with self.assertRaisesRegex(BoundaryError, "INTERACTIVE_WINDOWS_SESSIONS_REQUIRED"):
                    admit(Principal("S-1-5-21-1", owner_session), Principal("S-1-5-21-2", agent_session), "S-1-5-21-2")

    def test_same_sid_wrong_agent_and_bool_session_refused(self):
        for agent in (Principal("S-1-5-21-1", 3), Principal("S-1-5-21-3", 3), Principal("S-1-5-21-2", True)):
            with self.subTest(agent=agent), self.assertRaises(BoundaryError):
                admit(Principal("S-1-5-21-1", 2), agent, "S-1-5-21-2")

    def test_separate_selected_principals_validate_but_do_not_create_authority(self):
        self.assertIsNone(admit(Principal("S-1-5-21-1", 2), Principal("S-1-5-21-2", 3), "S-1-5-21-2"))
        with patch.object(probe, "current", return_value=Principal("S-1-5-21-1", 2)):
            report = probe.observe("owner", counterpart={"schema": "yc59-windows-actor-observation/v1",
                "role_label": "agent", "actor": {"sid": "S-1-5-21-2", "session_id": 3}})
        self.assertEqual(report["status"], "CANDIDATE_SEPARATE_SESSIONS_OBSERVED")
        self.assertFalse(report["report_is_authorization"])
        self.assertFalse(report["deployment_ready"])
        self.assertEqual(report["cloud_invocations"], 0)

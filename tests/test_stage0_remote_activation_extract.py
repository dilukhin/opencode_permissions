import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
MODULE_PATH = TOOLS / "stage0_remote_activation_extract.py"
spec = importlib.util.spec_from_file_location("stage0_remote_activation_extract", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class Stage0RemoteActivationExtractTests(unittest.TestCase):
    def test_auth_reports_wellknown_without_leaking_secret_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "auth.json"
            path.write_text(
                json.dumps(
                    {
                        "https://secret.example": {
                            "type": "wellknown",
                            "key": "SECRET_KEY",
                            "token": "SECRET_TOKEN",
                        },
                        "provider": {"type": "api", "key": "OTHER_SECRET"},
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"OPENCODE_AUTH_CONTENT": ""}, clear=False):
                result = mod.inspect_auth(path)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["wellknown_auth_present"])
        rendered = json.dumps(result)
        self.assertNotIn("SECRET_KEY", rendered)
        self.assertNotIn("SECRET_TOKEN", rendered)
        self.assertNotIn("secret.example", rendered)

    def test_auth_env_override_is_presence_only_and_blocks_determination(self):
        secret = '{"provider":{"type":"wellknown","token":"SECRET"}}'
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"OPENCODE_AUTH_CONTENT": secret}, clear=False
        ):
            result = mod.inspect_auth(Path(td) / "auth.json")
        self.assertEqual(result["status"], "blocked_env_override")
        self.assertIsNone(result["wellknown_auth_present"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("SECRET", json.dumps(result))

    def test_database_active_org_is_boolean_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opencode.db"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TABLE account_state (id INTEGER PRIMARY KEY, active_account_id TEXT, active_org_id TEXT)"
                )
                connection.execute(
                    "INSERT INTO account_state(id, active_account_id, active_org_id) VALUES (1, ?, ?)",
                    ("SECRET_ACCOUNT", "SECRET_ORG"),
                )
                connection.commit()
            finally:
                connection.close()
            result = mod.inspect_database(path)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["active_account_present"])
        self.assertTrue(result["active_org_present"])
        rendered = json.dumps(result)
        self.assertNotIn("SECRET_ACCOUNT", rendered)
        self.assertNotIn("SECRET_ORG", rendered)

    def test_database_without_account_state_is_not_active(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opencode.db"
            connection = sqlite3.connect(path)
            connection.close()
            result = mod.inspect_database(path)
        self.assertEqual(result["status"], "schema_absent")
        self.assertFalse(result["active_org_present"])

    def test_database_candidates_default_glob_and_override(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "opencode.db").write_bytes(b"")
            (root / "opencode-beta.db").write_bytes(b"")
            with mock.patch.dict(os.environ, {"OPENCODE_DB": ""}, clear=False):
                paths, mode = mod.database_candidates(root)
            self.assertEqual(mode, "default_glob")
            self.assertEqual([item.name for item in paths], ["opencode-beta.db", "opencode.db"])

            with mock.patch.dict(os.environ, {"OPENCODE_DB": "custom.db"}, clear=False):
                paths, mode = mod.database_candidates(root)
            self.assertEqual(mode, "OPENCODE_DB")
            self.assertEqual(paths, [root / "custom.db"])

    def test_build_output_never_retains_secret_or_identifier_values(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            mod, "data_dir", return_value=(Path(td), "test")
        ), mock.patch.dict(os.environ, {"OPENCODE_AUTH_CONTENT": "", "OPENCODE_DB": ""}, clear=False):
            payload = mod.build_output()
        self.assertFalse(payload["raw_auth_retained"])
        self.assertFalse(payload["secret_values_retained"])
        self.assertFalse(payload["account_identifier_values_retained"])
        self.assertFalse(payload["environment_values_retained"])
        self.assertTrue(payload["remote_activation"]["fully_determined"])
        self.assertFalse(payload["remote_activation"]["remote_permission_layer_activation_observed"])

    def test_memory_database_override_is_unknown_not_false(self):
        with mock.patch.dict(os.environ, {"OPENCODE_DB": ":memory:"}, clear=False):
            paths, mode = mod.database_candidates(Path("/unused"))
            active, reason = mod.aggregate_active_org([], mode)
        self.assertEqual(paths, [])
        self.assertEqual(mode, "memory_override")
        self.assertIsNone(active)
        self.assertIn(":memory:", reason)


if __name__ == "__main__":
    unittest.main()

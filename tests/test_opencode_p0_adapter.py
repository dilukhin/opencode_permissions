import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import opencode_p0_adapter as adapter  # noqa: E402


def runtime_profile(root: Path) -> Path:
    profile = {
        "schema": 1,
        "profile_format": "opencode-permissions-p0-classifier-profile/v1",
        "classifier_profile_id": "p0-linux-grep-single-file-v1",
        "platform": "linux",
        "shell": {"path": "/bin/dash"},
        "python_runtime": {"path": "/usr/bin/python3"},
        "executables": {"grep": {"path": "/usr/bin/grep", "semantic_name": "grep"}},
        "secret_boundary": {
            "resolved_rules": [
                {"id": "read.secret.deny.dotenv_root", "pattern": ".env", "action": "deny"},
                {"id": "read.secret.deny.dotenv_nested", "pattern": "*/.env", "action": "deny"},
                {"id": "read.secret_variant.ask.npmrc", "pattern": ".npmrc", "action": "ask"},
                {"id": "read.secret.deny.key_ext", "pattern": "*.key", "action": "deny"},
            ]
        },
        "target": {
            "opencode_version": "1.18.29",
            "compatibility_profile_id": "opencode-1.18.29-gate-b",
            "native_policy_artifact_id": "sha256:" + "1" * 64,
        },
    }
    path = root / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return path


class P0StaticParserTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "executables": {"grep": {"path": "/usr/bin/grep", "semantic_name": "grep"}},
        }

    def test_accepts_only_exact_three_token_grep_shape(self):
        argv, error = adapter._parse_static_grep("/usr/bin/grep NEEDLE notes.txt", self.profile)
        self.assertIsNone(error)
        self.assertEqual(argv, ["/usr/bin/grep", "NEEDLE", "notes.txt"])

    def test_rejects_options_dynamic_shell_and_compound_shapes(self):
        cases = [
            "/usr/bin/grep -r notes.txt",
            "/usr/bin/grep NEEDLE -n",
            "/usr/bin/grep 'NEEDLE' notes.txt",
            "/usr/bin/grep NEEDLE notes.txt | cat",
            "/usr/bin/grep NEEDLE notes.txt;id",
            "/usr/bin/grep $HOME notes.txt",
            "/usr/bin/grep NEEDLE *.txt",
            "/usr/bin/grep  NEEDLE notes.txt",
            "grep NEEDLE notes.txt",
            "/usr/bin/find . -type f",
            "/usr/bin/grep NEEDLE notes.txt extra.txt",
        ]
        for command in cases:
            with self.subTest(command=command):
                argv, error = adapter._parse_static_grep(command, self.profile)
                self.assertIsNone(argv)
                self.assertIsNotNone(error)

    def test_secret_wildcards_cover_root_nested_and_extension(self):
        profile = {
            "secret_boundary": {
                "resolved_rules": [
                    {"id": "root", "pattern": ".env", "action": "deny"},
                    {"id": "nested", "pattern": "*/.env", "action": "deny"},
                    {"id": "key", "pattern": "*.key", "action": "deny"},
                ]
            }
        }
        self.assertTrue(adapter._secret_rule_match(".env", profile)[0])
        self.assertTrue(adapter._secret_rule_match("a/.env", profile)[0])
        self.assertTrue(adapter._secret_rule_match("a/b/private.key", profile)[0])
        self.assertFalse(adapter._secret_rule_match("src/main.py", profile)[0])


@unittest.skipUnless(sys.platform == "linux", "P0 production runtime profile is Linux-only")
class P0LinuxRuntimeTests(unittest.TestCase):
    def setUp(self):
        for path in ("/bin/dash", "/usr/bin/grep", "/usr/bin/python3"):
            if not os.path.exists(path):
                self.skipTest(f"required P0 runtime path unavailable: {path}")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile = runtime_profile(self.root)
        (self.root / "notes.txt").write_text("alpha\nNEEDLE\nomega\n", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=synthetic\n", encoding="utf-8")
        (self.root / "nested").mkdir()
        (self.root / "nested" / ".env").write_text("TOKEN=synthetic\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_prepare_allows_one_existing_nonsecret_workspace_file(self):
        payload = adapter.prepare(
            "/usr/bin/grep NEEDLE notes.txt",
            str(self.root),
            str(self.root),
            str(self.profile),
        )
        result = payload["result"]
        guard = payload["guard"]
        self.assertEqual(result["decision"], "ALLOW")
        self.assertIsNotNone(guard)
        self.assertEqual(
            result["normalized_operation"]["execution"]["argv"],
            ["/usr/bin/grep", "NEEDLE", "notes.txt"],
        )
        self.assertEqual(
            result["normalized_operation"]["execution"]["executable"]["invoked"],
            "/usr/bin/grep",
        )
        self.assertEqual(len(result["normalized_operation"]["targets"]), 1)
        target = result["normalized_operation"]["targets"][0]
        self.assertEqual(target["kind"], "workspace_file")
        self.assertEqual(target["identity"]["sensitivity"], "nonsecret")
        self.assertEqual(result["operation_identity"], guard["operation_identity"])
        self.assertIn("adapter.p0_exact_grep_binding", result["reason_codes"])

    def test_secret_targets_are_never_classifier_allow(self):
        for requested in (".env", "nested/.env"):
            with self.subTest(requested=requested):
                payload = adapter.prepare(
                    f"/usr/bin/grep TOKEN {requested}",
                    str(self.root),
                    str(self.root),
                    str(self.profile),
                )
                self.assertEqual(payload["result"]["decision"], "DENY")
                self.assertIsNone(payload["guard"])
                self.assertIn("grep.secret_file", payload["result"]["reason_codes"])

    def test_external_missing_and_symlink_targets_fail_closed(self):
        outside = self.root.parent / (self.root.name + "-outside.txt")
        outside.write_text("NEEDLE\n", encoding="utf-8")
        try:
            external = adapter.prepare(
                f"/usr/bin/grep NEEDLE {outside}",
                str(self.root),
                str(self.root),
                str(self.profile),
            )
            self.assertEqual(external["result"]["decision"], "ASK_USER")
            self.assertIsNone(external["guard"])

            missing = adapter.prepare(
                "/usr/bin/grep NEEDLE missing.txt",
                str(self.root),
                str(self.root),
                str(self.profile),
            )
            self.assertEqual(missing["result"]["decision"], "ASK_USER")
            self.assertIsNone(missing["guard"])

            link = self.root / "link.txt"
            link.symlink_to(self.root / "notes.txt")
            symlink = adapter.prepare(
                "/usr/bin/grep NEEDLE link.txt",
                str(self.root),
                str(self.root),
                str(self.profile),
            )
            self.assertEqual(symlink["result"]["decision"], "ASK_USER")
            self.assertIsNone(symlink["guard"])
        finally:
            outside.unlink(missing_ok=True)

    def test_revalidation_detects_command_file_and_guard_drift(self):
        command = "/usr/bin/grep NEEDLE notes.txt"
        payload = adapter.prepare(command, str(self.root), str(self.root), str(self.profile))
        guard = payload["guard"]
        self.assertIsNotNone(guard)

        ok = adapter.revalidate(guard, command, str(self.root), str(self.root), str(self.profile))
        self.assertTrue(ok["ok"])

        changed_command = adapter.revalidate(
            guard,
            "/usr/bin/grep alpha notes.txt",
            str(self.root),
            str(self.root),
            str(self.profile),
        )
        self.assertFalse(changed_command["ok"])
        self.assertEqual(changed_command["reason"], "guard.command_mismatch")

        (self.root / "notes.txt").write_text("alpha\nNEEDLE\nomega\nchanged\n", encoding="utf-8")
        changed_file = adapter.revalidate(guard, command, str(self.root), str(self.root), str(self.profile))
        self.assertFalse(changed_file["ok"])
        self.assertEqual(changed_file["reason"], "guard.target_changed")

        forged = copy.deepcopy(adapter.prepare(command, str(self.root), str(self.root), str(self.profile))["guard"])
        forged["operation_identity"] = "sha256:" + "0" * 64
        mismatch = adapter.revalidate(forged, command, str(self.root), str(self.root), str(self.profile))
        self.assertFalse(mismatch["ok"])
        self.assertEqual(mismatch["reason"], "guard.operation_identity_changed")


if __name__ == "__main__":
    unittest.main()

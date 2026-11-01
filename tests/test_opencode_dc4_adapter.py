import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import opencode_dc4_adapter as adapter  # noqa: E402


class DC4StaticParserTests(unittest.TestCase):
    def test_accepts_only_static_space_delimited_absolute_command(self):
        argv, error = adapter._parse_static_simple("/usr/bin/printf DC4_OK")
        self.assertIsNone(error)
        self.assertEqual(argv, ["/usr/bin/printf", "DC4_OK"])

    def test_rejects_dynamic_shell_constructs(self):
        cases = [
            "/usr/bin/printf $HOME",
            "/usr/bin/printf $(id)",
            "/usr/bin/printf ok;id",
            "/usr/bin/printf ok | cat",
            "/usr/bin/printf >out",
            "/usr/bin/printf 'quoted'",
            "/usr/bin/printf  two-spaces",
            "printf DC4_OK",
        ]
        for command in cases:
            with self.subTest(command=command):
                argv, error = adapter._parse_static_simple(command)
                self.assertIsNone(argv)
                self.assertIsNotNone(error)

    def test_unknown_absolute_executable_is_not_allowlisted(self):
        executable, error = adapter._trusted_executable("/tmp/printf")
        self.assertIsNone(executable)
        self.assertEqual(error, "executable.not_allowlisted")

    def test_symlink_executable_is_rejected_before_content_binding(self):
        with mock.patch.object(adapter.os.path, "realpath", return_value="/synthetic/printf-target"), \
             mock.patch.object(adapter.os, "stat", return_value=SimpleNamespace(st_mode=0o100755, st_uid=0)), \
             mock.patch.object(adapter.os, "access", return_value=True), \
             mock.patch.object(adapter, "_sha256_file") as digest:
            executable, error = adapter._trusted_executable("/usr/bin/printf")
        self.assertIsNone(executable)
        self.assertEqual(error, "identity.executable_symlink_unsupported")
        digest.assert_not_called()


@unittest.skipUnless(sys.platform == "linux", "DC-4 exact runtime profile is Linux-only")
class DC4LinuxIdentityTests(unittest.TestCase):
    def setUp(self):
        if not (os.path.exists("/bin/dash") and os.path.exists("/usr/bin/printf")):
            self.skipTest("required exact DC-4 system executables are unavailable")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def require_non_alias_profile(self):
        # Newer runner images may use a multi-call binary via a symlink. The
        # runtime intentionally rejects that shape. Positive identity proof is
        # also required on the explicitly pinned Ubuntu 24.04 CI matrix.
        _executable, error = adapter._trusted_executable("/usr/bin/printf")
        if error == "identity.executable_symlink_unsupported":
            if os.environ.get("OPENCODE_DC4_REQUIRE_EXACT_PROFILE") == "1":
                self.fail("required DC-4 non-symlink printf profile is unavailable")
            self.skipTest("exact DC-4 non-symlink printf profile unavailable; covered on ubuntu-24.04")

    def test_prepare_rebinds_classifier_allow_to_exact_absolute_argv(self):
        self.require_non_alias_profile()
        payload = adapter.prepare("/usr/bin/printf DC4_OK", self.root, self.root, "/bin/dash")
        result = payload["result"]
        guard = payload["guard"]
        self.assertEqual(result["decision"], "ALLOW", payload)
        self.assertIsNotNone(guard)
        self.assertEqual(
            result["normalized_operation"]["execution"]["argv"],
            ["/usr/bin/printf", "DC4_OK"],
        )
        self.assertEqual(
            result["normalized_operation"]["execution"]["executable"]["invoked"],
            "/usr/bin/printf",
        )
        self.assertEqual(result["operation_identity"], guard["operation_identity"])
        self.assertIn("adapter.exact_executable_binding", result["reason_codes"])

    def test_prepare_rejects_untrusted_or_unsupported_shape(self):
        payload = adapter.prepare("/tmp/printf DC4_OK", self.root, self.root, "/bin/dash")
        self.assertEqual(payload["result"]["decision"], "ASK_USER")
        self.assertIsNone(payload["guard"])
        self.assertIn("executable.not_allowlisted", payload["result"]["uncertainties"])

    def test_revalidation_binds_command_and_object_identity(self):
        self.require_non_alias_profile()
        payload = adapter.prepare("/usr/bin/printf DC4_OK", self.root, self.root, "/bin/dash")
        guard = payload["guard"]
        self.assertIsNotNone(guard, payload)
        ok = adapter.revalidate(
            guard,
            "/usr/bin/printf DC4_OK",
            self.root,
            self.root,
            "/bin/dash",
        )
        self.assertTrue(ok["ok"])

        changed = adapter.revalidate(
            guard,
            "/usr/bin/printf DC4_CHANGED",
            self.root,
            self.root,
            "/bin/dash",
        )
        self.assertFalse(changed["ok"])
        self.assertEqual(changed["reason"], "guard.command_mismatch")

        forged = copy.deepcopy(guard)
        forged["operation_identity"] = "sha256:" + "0" * 64
        mismatch = adapter.revalidate(
            forged,
            "/usr/bin/printf DC4_OK",
            self.root,
            self.root,
            "/bin/dash",
        )
        self.assertFalse(mismatch["ok"])
        self.assertEqual(mismatch["reason"], "guard.operation_identity_changed")


if __name__ == "__main__":
    unittest.main()

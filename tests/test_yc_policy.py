import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import classifier_analyzers as analyzers  # noqa: E402
import classifier_core as core  # noqa: E402
import normalized_operation_identity as identity  # noqa: E402


CORPUS = ROOT / "tests" / "yc_cases.json"


def fact(command, *, parser_status="exact"):
    argv = command.split()
    return {
        "schema": "parsed-simple/v1",
        "platform": "windows",
        "parser": {"status": parser_status, "profile": "synthetic-yc-v1"},
        "executable": {
            "invoked": argv[0] if argv else "yc",
            "resolved_path": "C:/soft/yc/yc.exe",
            "object_identity": "synthetic:yc.exe",
        },
        "argv": argv,
        "cwd": {"lexical": "C:/repo", "object_identity": "synthetic:cwd", "follow_mode": "target"},
        "targets": [],
        "redirects": [],
        "stdin": {"kind": "none"},
    }


class YcPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]

    def classify(self, command, *, parser_status="exact"):
        return analyzers.analyze_simple(fact(command, parser_status=parser_status))

    def test_corpus(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(self.classify(case["command"])["decision"], case["expected_decision"])

    def test_native_deny_is_terminal(self):
        result = self.classify("yc compute instance list")
        self.assertEqual(core.combine_native_classifier("deny", result), {"decision": "DENY", "source": "native"})

    def test_guard_control_variants_are_terminal_deny_without_blanket_guard_deny(self):
        for command in (
            "yc --guard approve request",
            "yc --verbose --guard approve request",
            "yc --guard uninstall",
            "yc --verbose --guard uninstall",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command)["decision"], "DENY")
        self.assertEqual(self.classify("yc --guard status")["decision"], "ASK_USER")

    def test_allow_operations_have_exact_identity_and_effects(self):
        for command in (
            "yc compute instance list",
            "yc compute instance get --id epd42hrnss08t2440g90",
            "yc compute disk list",
            "yc compute instance start --id epd42hrnss08t2440g90",
            "yc compute instance stop --id epd42hrnss08t2440g90",
        ):
            result = self.classify(command)
            self.assertEqual(result["decision"], "ALLOW")
            self.assertRegex(result["operation_identity"], r"^sha256:[0-9a-f]{64}$")
            self.assertIn("process", result["effects"])
            self.assertIn("network", result["effects"])
            self.assertNotIn("unknown", result["effects"])

    def test_state_change_effects_are_honest(self):
        start = self.classify("yc compute instance start --id epd42hrnss08t2440g90")
        stop = self.classify("yc compute instance stop --id epd42hrnss08t2440g90")
        self.assertEqual(start["effects"], ["cloud_state_change", "network", "process"])
        self.assertEqual(stop["effects"], ["cloud_state_change", "network", "process"])

    def test_iam_listing_and_control_are_ask_user(self):
        for command in (
            "yc iam service-account list",
            "yc iam key list",
            "yc iam service-account create --name synthetic-sa",
            "yc iam service-account delete --id sa1",
            "yc iam service-account update --id sa1 --name renamed",
            "yc resource-manager folder add-access-binding --id folder1 --role viewer --subject serviceAccount:sa1",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command)["decision"], "ASK_USER")

    def test_identity_changes_for_action_target_and_argv(self):
        start = self.classify("yc compute instance start --id epd42hrnss08t2440g90")
        stop = self.classify("yc compute instance stop --id epd42hrnss08t2440g90")
        other = self.classify("yc compute instance start --id other")
        extra = self.classify("yc compute instance start --id epd42hrnss08t2440g90 --quiet")
        self.assertNotEqual(start["operation_identity"], stop["operation_identity"])
        self.assertNotEqual(start["operation_identity"], other["operation_identity"])
        self.assertNotEqual(start["operation_identity"], extra["operation_identity"])
        self.assertNotEqual(extra["decision"], "ALLOW")

    def test_opaque_and_unknown_cannot_allow(self):
        for command in ("yc compute instance start --id", "yc unknown command", "yc"):
            self.assertEqual(self.classify(command)["decision"], "ASK_USER")
        self.assertEqual(self.classify("yc compute instance list", parser_status="opaque")["decision"], "ASK_USER")

    def test_safety_metrics(self):
        rows = [(case, self.classify(case["command"])) for case in self.cases]
        self.assertEqual(sum(r["decision"] == "ALLOW" and c["safety"] != "safe" for c, r in rows), 0)
        self.assertEqual(sum(r["decision"] == "ALLOW" and c["safety"] == "dangerous" for c, r in rows), 0)
        self.assertEqual(sum(r["decision"] == "ALLOW" and c["safety"] == "secret" for c, r in rows), 0)
        self.assertEqual(sum(r["decision"] == "ALLOW" and c["safety"] == "unknown" for c, r in rows), 0)
        self.assertEqual(sum(c["expected_decision"] == "DENY" and r["decision"] != "DENY" for c, r in rows), 0)
        self.assertEqual(sum(r["decision"] == "ALLOW" and r.get("operation_identity") is None for _, r in rows), 0)

    def test_identity_helper_agrees_with_core_result(self):
        result = self.classify("yc compute instance start --id epd42hrnss08t2440g90")
        self.assertEqual(result["operation_identity"], identity.operation_identity(result["normalized_operation"]))


if __name__ == "__main__":
    unittest.main()

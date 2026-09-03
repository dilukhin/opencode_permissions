import copy
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import classifier_analyzers as analyzers  # noqa: E402
import classifier_core as core  # noqa: E402

CASES = ROOT / "tests" / "classifier_cases" / "dc2_cases.json"


def lexical_for(kind, requested):
    if kind == "system_path":
        return requested
    if requested == ".":
        return "/repo"
    return "/repo/" + requested.lstrip("/")


def build_target(case_id, descriptor, index=0):
    requested = descriptor["requested"]
    kind = descriptor["kind"]
    identity = {
        "requested": requested,
        "lexical": lexical_for(kind, requested),
        "object_identity": f"synthetic:{case_id}:{index}:{kind}",
        "follow_mode": "target",
        "boundary": "system" if kind == "system_path" else "workspace",
    }
    if "sensitivity" in descriptor:
        identity["sensitivity"] = descriptor["sensitivity"]
    return {
        "role": descriptor["role"],
        "kind": kind,
        "identity": identity,
    }


def build_simple_fact(case):
    argv = list(case["argv"])
    case_id = case["id"]
    targets = [build_target(case_id, item, i) for i, item in enumerate(case.get("targets", []))]
    redirects = []
    for i, redirect in enumerate(case.get("redirects", [])):
        redirects.append(
            {
                "kind": redirect["kind"],
                "target": build_target(case_id + ":redirect", redirect["target"], i),
            }
        )
    fact = {
        "schema": "parsed-simple/v1",
        "platform": "linux",
        "parser": {
            "status": case.get("parser_status", "exact"),
            "profile": "synthetic-dc2-v1",
        },
        "executable": {
            "invoked": argv[0],
            "resolved_path": f"/usr/bin/{argv[0]}",
            "object_identity": f"synthetic:exe:{argv[0]}",
        },
        "argv": argv,
        "cwd": {
            "lexical": "/repo",
            "object_identity": "synthetic:cwd:repo",
            "follow_mode": "target",
            "boundary": "workspace",
        },
        "targets": targets,
        "redirects": redirects,
        "stdin": {"kind": case.get("stdin", "none")},
    }
    return fact


class DC2AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projection = json.loads(CASES.read_text(encoding="utf-8"))
        cls.by_id = {case["id"]: case for case in cls.projection["cases"]}
        cls.simple_facts = {
            case["id"]: build_simple_fact(case)
            for case in cls.projection["cases"]
            if case["mode"] == "simple"
        }

    def analyzer_result(self, case):
        if case["mode"] == "simple":
            return analyzers.analyze_simple(copy.deepcopy(self.simple_facts[case["id"]]))
        children = [copy.deepcopy(self.simple_facts[child]) for child in case["children"]]
        if case["mode"] == "compound":
            return analyzers.analyze_compound(children, list(case["operators"]))
        if case["mode"] == "pipeline":
            return analyzers.analyze_pipeline(children, list(case["pipes"]))
        raise AssertionError(f"unsupported mode {case['mode']}")

    def combined(self, case):
        result = self.analyzer_result(case)
        return core.combine_native_classifier(case["native_decision"], result), result

    def test_projection_shape_and_expected_combined_decisions(self):
        self.assertEqual(self.projection["case_count"], len(self.projection["cases"]))
        self.assertEqual(len(self.by_id), self.projection["case_count"])
        for case in self.projection["cases"]:
            with self.subTest(case=case["id"]):
                combined, _ = self.combined(case)
                self.assertEqual(combined["decision"], case["expected_combined"])

    def test_hardened_git_diff_allows_but_plain_diff_stays_ask(self):
        hardened = self.analyzer_result(self.by_id["git_diff_hardened"])
        plain = self.analyzer_result(self.by_id["git_diff_plain"])
        self.assertEqual(hardened["decision"], "ALLOW")
        self.assertRegex(hardened["operation_identity"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(plain["decision"], "ASK_USER")
        self.assertIn("git.diff.transforms_unconstrained", plain["uncertainties"])

    def test_find_readonly_promotes_and_exec_delete_do_not(self):
        self.assertEqual(self.analyzer_result(self.by_id["find_print"])["decision"], "ALLOW")
        self.assertEqual(self.analyzer_result(self.by_id["find_delete"])["decision"], "DENY")
        nested = self.analyzer_result(self.by_id["find_exec"])
        self.assertEqual(nested["decision"], "ASK_USER")
        self.assertIn("unknown_code_execution", nested["effects"])

    def test_single_nonsecret_grep_allows_secret_denies_recursive_asks(self):
        self.assertEqual(self.analyzer_result(self.by_id["grep_single_nonsecret"])["decision"], "ALLOW")
        secret = self.analyzer_result(self.by_id["grep_secret"])
        self.assertEqual(secret["decision"], "DENY")
        self.assertIn("secrets", secret["effects"])
        self.assertEqual(self.analyzer_result(self.by_id["grep_recursive"])["decision"], "ASK_USER")

    def test_system_write_denies_workspace_write_asks(self):
        system = self.analyzer_result(self.by_id["touch_system"])
        workspace = self.analyzer_result(self.by_id["touch_workspace"])
        self.assertEqual(system["decision"], "DENY")
        self.assertIn("system", system["effects"])
        self.assertEqual(workspace["decision"], "ASK_USER")

    def test_build_and_test_commands_remain_unknown_code_execution(self):
        for case_id in ("cmake_build", "ctest", "pytest"):
            with self.subTest(case=case_id):
                result = self.analyzer_result(self.by_id[case_id])
                self.assertEqual(result["decision"], "ASK_USER")
                self.assertIn("unknown_code_execution", result["effects"])

    def test_opaque_parser_cannot_allow(self):
        result = self.analyzer_result(self.by_id["opaque_parser"])
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertIsNone(result["operation_identity"])
        self.assertIn("syntax.opaque", result["uncertainties"])

    def test_redirect_write_is_explicit_and_system_redirect_denies(self):
        workspace = self.analyzer_result(self.by_id["redirect_workspace"])
        system = self.analyzer_result(self.by_id["redirect_system"])
        self.assertEqual(workspace["decision"], "ASK_USER")
        self.assertIn("write", workspace["effects"])
        self.assertEqual(system["decision"], "DENY")
        self.assertIn("system", system["effects"])

    def test_compound_and_pipeline_use_dc1_parent_identity(self):
        compound = self.analyzer_result(self.by_id["compound_pwd_find"])
        pipeline = self.analyzer_result(self.by_id["pipeline_printf_grep"])
        self.assertEqual(compound["decision"], "ALLOW")
        self.assertEqual(compound["normalized_operation"]["operation_kind"], "compound")
        self.assertEqual(pipeline["decision"], "ALLOW")
        self.assertEqual(pipeline["normalized_operation"]["operation_kind"], "pipeline")

    def test_compound_danger_and_unknown_dominate(self):
        self.assertEqual(self.analyzer_result(self.by_id["compound_system_write"])["decision"], "DENY")
        self.assertEqual(self.analyzer_result(self.by_id["compound_unknown"])["decision"], "ASK_USER")

    def test_safety_metrics(self):
        rows = []
        for case in self.projection["cases"]:
            combined, classifier = self.combined(case)
            rows.append((case, combined, classifier))

        unsafe_auto_allow = sum(
            combined["decision"] == "ALLOW" and case["safety"] != "safe"
            for case, combined, _ in rows
        )
        dangerous_false_safe = sum(
            combined["decision"] == "ALLOW" and case["safety"] == "deny"
            for case, combined, _ in rows
        )
        unknown_false_safe = sum(
            combined["decision"] == "ALLOW" and "unknown" in case.get("tags", [])
            for case, combined, _ in rows
        )
        secret_false_safe = sum(
            combined["decision"] == "ALLOW" and "secret" in case.get("tags", [])
            for case, combined, _ in rows
        )
        native_deny_override = sum(
            case["native_decision"] == "deny" and combined["decision"] != "DENY"
            for case, combined, _ in rows
        )
        unparsed_auto_allow = sum(
            case.get("parser_status") == "opaque" and combined["decision"] == "ALLOW"
            for case, combined, _ in rows
        )
        identityless_auto_allow = sum(
            case["native_decision"] == "ask"
            and classifier["decision"] == "ALLOW"
            and not classifier.get("operation_identity")
            for case, _, classifier in rows
        )
        sound_safe_promotions = sum(
            case["native_decision"] == "ask"
            and case["safety"] == "safe"
            and combined["decision"] == "ALLOW"
            for case, combined, _ in rows
        )

        self.assertEqual(unsafe_auto_allow, 0)
        self.assertEqual(dangerous_false_safe, 0)
        self.assertEqual(unknown_false_safe, 0)
        self.assertEqual(secret_false_safe, 0)
        self.assertEqual(native_deny_override, 0)
        self.assertEqual(unparsed_auto_allow, 0)
        self.assertEqual(identityless_auto_allow, 0)
        self.assertGreaterEqual(sound_safe_promotions, 7)


if __name__ == "__main__":
    unittest.main()

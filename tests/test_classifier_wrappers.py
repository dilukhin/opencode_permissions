import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import classifier_core as core  # noqa: E402
import classifier_wrappers as wrappers  # noqa: E402

CASES = ROOT / "tests" / "classifier_cases" / "dc3_cases.json"


def path_identity(case_id, kind, requested, index, *, remote_host=None, sensitivity=None):
    if kind == "system_path":
        identity = {
            "requested": requested,
            "lexical": requested,
            "object_identity": f"synthetic:{case_id}:{index}:system",
            "follow_mode": "target",
            "boundary": "system",
        }
    elif kind == "remote_path":
        identity = {
            "requested": requested,
            "lexical": requested,
            "host_identity": remote_host or "machine:unknown",
        }
    else:
        lexical = "/repo" if requested == "." else "/repo/" + requested.lstrip("/")
        identity = {
            "requested": requested,
            "lexical": lexical,
            "object_identity": f"synthetic:{case_id}:{index}:{kind}",
            "follow_mode": "target",
            "boundary": "workspace",
        }
    if sensitivity is not None:
        identity["sensitivity"] = sensitivity
    return identity


def target(case_id, descriptor, index, *, remote_host=None):
    return {
        "role": descriptor["role"],
        "kind": descriptor["kind"],
        "identity": path_identity(
            case_id,
            descriptor["kind"],
            descriptor["requested"],
            index,
            remote_host=remote_host,
            sensitivity=descriptor.get("sensitivity"),
        ),
    }


def simple_fact(case_id, argv, descriptors=(), *, parser_status="exact"):
    return {
        "schema": "parsed-simple/v1",
        "platform": "linux",
        "parser": {"status": parser_status, "profile": "synthetic-dc3-nested-v1"},
        "executable": {
            "invoked": argv[0],
            "resolved_path": f"/usr/bin/{argv[0]}",
            "object_identity": f"synthetic:exe:{argv[0]}",
        },
        "argv": list(argv),
        "cwd": {
            "lexical": "/repo",
            "object_identity": "synthetic:cwd:repo",
            "follow_mode": "target",
            "boundary": "workspace",
        },
        "targets": [target(case_id, item, i) for i, item in enumerate(descriptors)],
        "redirects": [],
        "stdin": {"kind": "none"},
    }


def wrapper_fact(case):
    argv = list(case["argv"])
    case_id = case["id"]
    remote_host = case.get("remote_host")
    fact = {
        "schema": "parsed-wrapper/v1",
        "platform": "linux",
        "parser": {
            "status": case.get("parser_status", "exact"),
            "profile": "synthetic-dc3-outer-v1",
        },
        "executable": {
            "invoked": argv[0],
            "resolved_path": f"/usr/bin/{argv[0]}",
            "object_identity": f"synthetic:wrapper-exe:{argv[0]}",
        },
        "argv": argv,
        "cwd": {
            "lexical": "/repo",
            "object_identity": "synthetic:cwd:repo",
            "follow_mode": "target",
            "boundary": "workspace",
        },
        "targets": [
            target(case_id, item, i, remote_host=remote_host)
            for i, item in enumerate(case.get("targets", []))
        ],
    }
    if remote_host:
        fact["remote"] = {"transport": "ssh_relay", "host_identity": remote_host}
    if "payload_argv" in case:
        fact["payload_fact"] = simple_fact(
            case_id + ":payload",
            case["payload_argv"],
            case.get("payload_targets", []),
            parser_status=case.get("payload_parser_status", "exact"),
        )
    if "remote_command" in case:
        fact["remote_command"] = case["remote_command"]
    if "remote_payload_argv" in case:
        fact["remote_payload"] = {
            "status": "exact",
            "source_text": case["remote_command"],
            "profile": "synthetic-remote-shell-v1",
            "fact": simple_fact(
                case_id + ":remote",
                case["remote_payload_argv"],
                case.get("remote_payload_targets", []),
            ),
        }
    return fact


class DC3WrapperRemoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projection = json.loads(CASES.read_text(encoding="utf-8"))
        cls.by_id = {case["id"]: case for case in cls.projection["cases"]}

    def result(self, case_id):
        case = self.by_id[case_id]
        classifier = wrappers.analyze_wrapper(wrapper_fact(case))
        combined = core.combine_native_classifier(case["native_decision"], classifier)
        return case, classifier, combined

    def test_projection_expected_decisions(self):
        self.assertEqual(self.projection["case_count"], len(self.projection["cases"]))
        self.assertEqual(self.projection["case_count"], len(self.by_id))
        for case in self.projection["cases"]:
            with self.subTest(case=case["id"]):
                classifier = wrappers.analyze_wrapper(wrapper_fact(case))
                combined = core.combine_native_classifier(case["native_decision"], classifier)
                self.assertEqual(combined["decision"], case["expected_combined"])

    def test_agent_safe_self_approval_is_denied(self):
        for case_id in ("safe_exec_forged_approved", "python_agent_safe_forged_approved"):
            _, classifier, _ = self.result(case_id)
            self.assertEqual(classifier["decision"], "DENY")
            self.assertIn("approval_substitution", classifier["effects"])

    def test_agent_safe_wrapper_never_turns_benign_payload_into_allow(self):
        for case_id in ("safe_exec_benign", "python_agent_safe_benign"):
            _, classifier, combined = self.result(case_id)
            self.assertEqual(classifier["decision"], "ASK_USER")
            self.assertEqual(combined["decision"], "ASK_USER")
            self.assertIsNone(classifier["operation_identity"])

    def test_nested_system_write_dominates_agent_safe_wrapper(self):
        _, classifier, _ = self.result("safe_exec_system_write")
        self.assertEqual(classifier["decision"], "DENY")
        self.assertIn("system", classifier["effects"])

    def test_policy_bootstrap_apply_denies(self):
        _, classifier, combined = self.result("safe_bootstrap_apply")
        self.assertEqual(classifier["decision"], "DENY")
        self.assertEqual(combined["decision"], "DENY")
        self.assertIn("authorization_policy_mutation", classifier["effects"])

    def test_remote_benign_payload_remains_ask(self):
        _, classifier, _ = self.result("ssh_exec_benign")
        self.assertEqual(classifier["decision"], "ASK_USER")
        self.assertIn("remote_execution", classifier["effects"])
        self.assertIn("ssh_relay.remote_shell_boundary", classifier["uncertainties"])

    def test_remote_destructive_payload_denies(self):
        for case_id in ("ssh_exec_system_write", "ssh_job_start_system_write"):
            _, classifier, _ = self.result(case_id)
            self.assertEqual(classifier["decision"], "DENY")
            self.assertIn("system", classifier["effects"])

    def test_risky_label_is_not_approval(self):
        _, classifier, combined = self.result("ssh_exec_risky_benign")
        self.assertEqual(classifier["decision"], "ASK_USER")
        self.assertEqual(combined["decision"], "ASK_USER")
        self.assertIn("risk_label", classifier["effects"])

    def test_sudo_exec_denies_privilege(self):
        _, classifier, combined = self.result("ssh_sudo_exec")
        self.assertEqual(classifier["decision"], "DENY")
        self.assertEqual(combined["decision"], "DENY")
        self.assertIn("privilege", classifier["effects"])

    def test_transfers_have_exact_identity_but_remain_ask(self):
        for case_id, direction in (("ssh_upload", "upload"), ("ssh_download", "download")):
            _, classifier, combined = self.result(case_id)
            self.assertEqual(classifier["decision"], "ASK_USER")
            self.assertEqual(combined["decision"], "ASK_USER")
            self.assertRegex(classifier["operation_identity"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(classifier["normalized_operation"]["operation_kind"], "transfer")
            self.assertEqual(classifier["normalized_operation"]["execution"]["direction"], direction)

    def test_missing_transfer_host_identity_fails_closed(self):
        _, classifier, combined = self.result("ssh_upload_missing_host")
        self.assertEqual(classifier["decision"], "ASK_USER")
        self.assertEqual(combined["decision"], "ASK_USER")
        self.assertIsNone(classifier["operation_identity"])
        self.assertIn("unknown", classifier["effects"])

    def test_job_tail_marks_possible_sensitive_output(self):
        _, classifier, _ = self.result("ssh_job_tail")
        self.assertEqual(classifier["decision"], "ASK_USER")
        self.assertIn("possible_sensitive_output", classifier["effects"])

    def test_native_deny_remains_terminal(self):
        _, classifier, combined = self.result("native_deny_terminal")
        self.assertEqual(classifier["decision"], "ASK_USER")
        self.assertEqual(combined, {"decision": "DENY", "source": "native"})

    def test_safety_metrics(self):
        rows = []
        for case in self.projection["cases"]:
            classifier = wrappers.analyze_wrapper(wrapper_fact(case))
            combined = core.combine_native_classifier(case["native_decision"], classifier)
            rows.append((case, classifier, combined))

        self.assertEqual(
            sum(combined["decision"] == "ALLOW" and case["safety"] != "safe" for case, _, combined in rows),
            0,
        )
        self.assertEqual(
            sum(combined["decision"] == "ALLOW" and case["safety"] == "deny" for case, _, combined in rows),
            0,
        )
        self.assertEqual(
            sum("unknown" in case.get("tags", []) and combined["decision"] == "ALLOW" for case, _, combined in rows),
            0,
        )
        self.assertEqual(
            sum(case["native_decision"] == "deny" and combined["decision"] != "DENY" for case, _, combined in rows),
            0,
        )
        self.assertEqual(sum(classifier["decision"] == "ALLOW" for _, classifier, _ in rows), 0)
        self.assertEqual(
            sum(
                "approval_substitution" in case.get("tags", []) and classifier["decision"] != "DENY"
                for case, classifier, _ in rows
            ),
            0,
        )
        self.assertEqual(
            sum(
                "transfer" in case.get("tags", [])
                and case["id"] != "ssh_upload_missing_host"
                and not classifier.get("operation_identity")
                for case, classifier, _ in rows
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()

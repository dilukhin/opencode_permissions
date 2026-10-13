import copy
import json
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import classifier_core as core  # noqa: E402
import classifier_wrappers as wrappers  # noqa: E402

BROKER_MODULE = ROOT / "tests" / "authorization_broker" / "state_model.py"
_broker_spec = importlib.util.spec_from_file_location("sudo_job_broker_state_model", BROKER_MODULE)
broker_state = importlib.util.module_from_spec(_broker_spec)
assert _broker_spec.loader is not None
_broker_spec.loader.exec_module(broker_state)

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
    if "sudo_job_identity" in case:
        fact["sudo_job_identity"] = copy.deepcopy(case["sudo_job_identity"])
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

    def test_sudo_job_start_has_exact_identity_but_remains_ask(self):
        _, classifier, combined = self.result("ssh_sudo_job_start_benign")
        self.assertEqual("ASK_USER", classifier["decision"])
        self.assertEqual("ASK_USER", combined["decision"])
        self.assertRegex(classifier["operation_identity"], r"^sha256:[0-9a-f]{64}$")
        operation = classifier["normalized_operation"]
        self.assertEqual("remote_exec", operation["operation_kind"])
        self.assertEqual("start", operation["execution"]["sudo_job_operation"])
        self.assertEqual("root", operation["execution"]["privilege"])
        self.assertEqual("remote_argv", operation["execution"]["kind"])
        self.assertEqual(operation["execution"]["command_sha256"], operation["execution"]["argv"][-1])

    def test_sudo_job_destructive_child_denies(self):
        _, classifier, combined = self.result("ssh_sudo_job_start_system_write")
        self.assertEqual("DENY", classifier["decision"])
        self.assertEqual("DENY", combined["decision"])
        self.assertIn("system", classifier["effects"])

    def test_sudo_job_read_and_stop_remain_ask(self):
        for case_id in ("ssh_sudo_job_status", "ssh_sudo_job_tail", "ssh_sudo_job_stop"):
            with self.subTest(case_id=case_id):
                _, classifier, combined = self.result(case_id)
                self.assertEqual("ASK_USER", classifier["decision"])
                self.assertEqual("ASK_USER", combined["decision"])
                self.assertRegex(classifier["operation_identity"], r"^sha256:[0-9a-f]{64}$")
        _, tail, _ = self.result("ssh_sudo_job_tail")
        self.assertIn("possible_sensitive_output", tail["effects"])
        _, stop, _ = self.result("ssh_sudo_job_stop")
        self.assertIn("process_control", stop["effects"])
        self.assertIn("privilege", stop["effects"])

    def test_sudo_job_identity_file_is_not_self_approval(self):
        _, classifier, combined = self.result("ssh_sudo_job_missing_binding")
        self.assertEqual("ASK_USER", classifier["decision"])
        self.assertEqual("ASK_USER", combined["decision"])
        self.assertIsNone(classifier["operation_identity"])
        self.assertIn("unknown", classifier["effects"])

    def test_sudo_job_binding_drift_changes_or_removes_identity(self):
        case = copy.deepcopy(self.by_id["ssh_sudo_job_start_benign"])
        first = wrappers.analyze_wrapper(wrapper_fact(case))
        case["sudo_job_identity"]["value"]["verified_identity"]["connection_generation"] = 8
        changed = wrappers.analyze_wrapper(wrapper_fact(case))
        self.assertNotEqual(first["operation_identity"], changed["operation_identity"])
        case["sudo_job_identity"]["value"]["transaction_id"] = "33333333-3333-4333-8333-333333333333"
        mismatch = wrappers.analyze_wrapper(wrapper_fact(case))
        self.assertIsNone(mismatch["operation_identity"])
        self.assertEqual("ASK_USER", mismatch["decision"])

    def test_sudo_job_invocation_drift_cannot_reuse_one_time_grant(self):
        original = wrapper_fact(copy.deepcopy(self.by_id["ssh_sudo_job_tail"]))
        baseline = wrappers.analyze_wrapper(original)["operation_identity"]
        self.assertIsNotNone(baseline)
        variants = []
        for flag, value in (("--name", "other"), ("--stream", "stderr"), ("--bytes", "32")):
            changed = copy.deepcopy(original)
            if flag in changed["argv"]:
                changed["argv"][changed["argv"].index(flag) + 1] = value
            else:
                changed["argv"].extend([flag, value])
            variants.append(changed)
        for field in ("executable", "cwd"):
            changed = copy.deepcopy(original)
            changed[field]["object_identity"] += ":replaced"
            variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed):
                identity = wrappers.analyze_wrapper(changed)["operation_identity"]
                self.assertIsNotNone(identity)
                self.assertNotEqual(baseline, identity)
                broker = broker_state.BrokerStateModel()
                source = ("session", "message", "call")
                grant = broker.request("host-peer", baseline, source, "ASK_USER")
                broker.approve_once(grant)
                with self.assertRaises(broker_state.BrokerContractError):
                    broker.consume("pep-peer", grant, identity, source)

    def test_sudo_job_start_payload_must_match_actual_cli(self):
        case = copy.deepcopy(self.by_id["ssh_sudo_job_start_benign"])
        case["argv"][-1] = "touch /etc/example"
        result = wrappers.analyze_wrapper(wrapper_fact(case))
        self.assertEqual("ASK_USER", result["decision"])
        self.assertIsNone(result["operation_identity"])

    def test_sudo_job_unknown_duplicate_or_invalid_options_have_no_identity(self):
        case = self.by_id["ssh_sudo_job_tail"]
        for extra in (["--force"], ["--name", "prod"], ["--bytes", "65537"], ["--stream", "invalid"]):
            with self.subTest(extra=extra):
                fact = wrapper_fact(copy.deepcopy(case))
                fact["argv"].extend(extra)
                result = wrappers.analyze_wrapper(fact)
                self.assertEqual("ASK_USER", result["decision"])
                self.assertIsNone(result["operation_identity"])

    def test_sudo_job_one_time_grant_is_bound_to_exact_operation_identity(self):
        case = copy.deepcopy(self.by_id["ssh_sudo_job_start_benign"])
        exact = wrappers.analyze_wrapper(wrapper_fact(case))
        operation_identity = exact["operation_identity"]
        self.assertRegex(operation_identity, r"^sha256:[0-9a-f]{64}$")

        source = ("session-sudo-job", "message-1", "call-1")
        broker = broker_state.BrokerStateModel()
        authorization_id = broker.request("host-peer", operation_identity, source, "ASK_USER")
        broker.approve_once(authorization_id)

        changed_case = copy.deepcopy(case)
        changed_case["sudo_job_identity"]["value"]["verified_identity"]["connection_generation"] = 8
        changed = wrappers.analyze_wrapper(wrapper_fact(changed_case))
        self.assertNotEqual(operation_identity, changed["operation_identity"])
        with self.assertRaises(broker_state.BrokerContractError) as mismatch:
            broker.consume("pep-peer", authorization_id, changed["operation_identity"], source)
        self.assertEqual("OPERATION_IDENTITY_MISMATCH", mismatch.exception.code)

        self.assertEqual(
            "ALLOW_EXECUTION_ONCE",
            broker.consume("pep-peer", authorization_id, operation_identity, source),
        )
        with self.assertRaises(broker_state.BrokerContractError) as replay:
            broker.consume("pep-peer", authorization_id, operation_identity, source)
        self.assertEqual("GRANT_ALREADY_CONSUMED", replay.exception.code)

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

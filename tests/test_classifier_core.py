import copy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import classifier_core as core  # noqa: E402
import normalized_operation_identity as identity  # noqa: E402


def path_identity(path, object_id):
    return {"lexical": path, "object_identity": object_id, "follow_mode": "target"}


def target(path="/repo", object_id="posix:dev1:ino20", role="workspace", kind="directory"):
    return {"role": role, "kind": kind, "identity": path_identity(path, object_id)}


def process_operation(
    invoked="pwd",
    argv=None,
    effects=None,
    path="/repo",
    object_id="posix:dev1:ino20",
    executable_id=None,
    targets=None,
):
    argv = list(argv if argv is not None else [invoked])
    effects = list(effects if effects is not None else ["process"])
    executable_id = executable_id or f"posix:dev1:exe:{invoked}"
    targets = list(targets if targets is not None else [target(path, object_id)])
    return {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": "linux",
        "channel": "local",
        "operation_kind": "process_exec",
        "execution": {
            "kind": "argv",
            "executable": {
                "invoked": invoked,
                "resolved_path": f"/usr/bin/{invoked}",
                "object_identity": executable_id,
            },
            "argv": argv,
            "cwd": path_identity(path, object_id),
        },
        "targets": targets,
        "effects": effects,
        "context_dependencies": [],
    }


def compound_operation(children, *, effects=None, targets=None, operators=None):
    child_ids = [child["operation_identity"] for child in children]
    operators = list(operators if operators is not None else ["&&"] * (len(child_ids) - 1))
    if effects is None:
        effects = sorted({effect for child in children for effect in child["effects"]})
    if targets is None:
        by_key = {}
        for child in children:
            for item in child["targets"]:
                by_key[identity.jcs_dumps(item)] = copy.deepcopy(item)
        targets = [by_key[key] for key in sorted(by_key)]
    return {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": "linux",
        "channel": "local",
        "operation_kind": "compound",
        "execution": {
            "kind": "compound",
            "steps": child_ids,
            "operators": operators,
        },
        "targets": copy.deepcopy(targets),
        "effects": list(effects),
        "context_dependencies": [],
    }


class ClassifierCoreTests(unittest.TestCase):
    def assert_classifier_error(self, code, fn):
        with self.assertRaises(core.ClassifierError) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code)

    def test_valid_allow_has_complete_identity(self):
        operation = process_operation(effects=["read", "process"])
        result = core.allow_result(operation, reason_codes=["test.safe"])
        self.assertEqual(result["decision"], "ALLOW")
        self.assertRegex(result["operation_identity"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(result["effects"], ["process", "read"])
        self.assertEqual(result["uncertainties"], [])

    def test_allow_rejects_unknown_effect(self):
        operation = process_operation(effects=["process", "unknown"])
        self.assert_classifier_error(
            "ALLOW_WITH_UNKNOWN_EFFECT",
            lambda: core.allow_result(operation, reason_codes=["test.unknown"]),
        )

    def test_allow_rejects_unknown_target(self):
        unknown = {"role": "target", "kind": "unknown_target", "identity": {"canonical": "unknown"}}
        operation = process_operation(targets=[unknown])
        self.assert_classifier_error(
            "ALLOW_WITH_UNKNOWN_TARGET",
            lambda: core.allow_result(operation, reason_codes=["test.unknown_target"]),
        )

    def test_allow_requires_semantically_complete_operation(self):
        operation = process_operation()
        del operation["execution"]["argv"]
        self.assert_classifier_error(
            "ARGV_REQUIRED",
            lambda: core.allow_result(operation, reason_codes=["test.incomplete"]),
        )

    def test_result_identity_mismatch_is_rejected(self):
        result = core.allow_result(process_operation(), reason_codes=["test.safe"])
        result["operation_identity"] = "sha256:" + "0" * 64
        self.assert_classifier_error(
            "OPERATION_IDENTITY_MISMATCH",
            lambda: core.validate_result(result),
        )

    def test_result_effects_must_match_identity_core(self):
        result = core.allow_result(process_operation(), reason_codes=["test.safe"])
        result["effects"] = ["process", "write"]
        self.assert_classifier_error(
            "RESULT_EFFECTS_IDENTITY_MISMATCH",
            lambda: core.validate_result(result),
        )

    def test_native_deny_is_terminal_even_with_hypothetical_classifier_allow(self):
        classifier = core.allow_result(process_operation(), reason_codes=["test.safe"])
        combined = core.combine_native_classifier("deny", classifier)
        self.assertEqual(combined, {"decision": "DENY", "source": "native"})

    def test_native_allow_is_terminal_and_classifier_is_not_consulted(self):
        malformed_classifier = {"not": "a classifier result"}
        combined = core.combine_native_classifier("allow", malformed_classifier)
        self.assertEqual(combined, {"decision": "ALLOW", "source": "native"})

    def test_native_ask_without_classifier_stays_ask(self):
        self.assertEqual(
            core.combine_native_classifier("ask"),
            {"decision": "ASK_USER", "source": "native_ask_no_classifier"},
        )

    def test_native_ask_uses_valid_classifier_result(self):
        classifier = core.allow_result(process_operation(), reason_codes=["test.safe"])
        combined = core.combine_native_classifier("ask", classifier)
        self.assertEqual(combined["decision"], "ALLOW")
        self.assertEqual(combined["source"], "classifier")

    def test_composition_deny_dominates_ask(self):
        allow = core.allow_result(process_operation(), reason_codes=["child.allow"])
        ask = core.ask_result(
            reason_codes=["child.ask"],
            effects=["read"],
            targets=[],
            uncertainties=["syntax.opaque"],
        )
        deny = core.deny_result(reason_codes=["child.deny"], effects=["delete"], targets=[])
        result = core.compose_results([allow, ask, deny])
        self.assertEqual(result["decision"], "DENY")
        self.assertIn("composition.child_deny", result["reason_codes"])

    def test_composition_ask_dominates_allow(self):
        allow = core.allow_result(process_operation(), reason_codes=["child.allow"])
        ask = core.ask_result(
            reason_codes=["child.ask"],
            effects=["read"],
            targets=[],
            uncertainties=["syntax.opaque"],
        )
        result = core.compose_results([allow, ask])
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertIn("composition.child_uncertainty", result["uncertainties"])

    def test_all_allow_children_without_parent_identity_downgrade_to_ask(self):
        a = core.allow_result(process_operation("pwd"), reason_codes=["child.pwd"])
        b = core.allow_result(
            process_operation("git", argv=["git", "status", "--short"], effects=["process", "read", "git_read"]),
            reason_codes=["child.git_status"],
        )
        result = core.compose_results([a, b])
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertEqual(result["uncertainties"], ["identity.parent_missing"])

    def test_all_allow_children_with_complete_parent_can_allow(self):
        a = core.allow_result(process_operation("pwd"), reason_codes=["child.pwd"])
        b = core.allow_result(
            process_operation("git", argv=["git", "status", "--short"], effects=["process", "read", "git_read"]),
            reason_codes=["child.git_status"],
        )
        parent = compound_operation([a, b])
        result = core.compose_results([a, b], parent_operation=parent)
        self.assertEqual(result["decision"], "ALLOW")
        self.assertIn("composition.all_children_allow", result["reason_codes"])
        self.assertRegex(result["operation_identity"], r"^sha256:[0-9a-f]{64}$")

    def test_parent_missing_child_effect_downgrades_to_ask(self):
        a = core.allow_result(process_operation("pwd", effects=["process", "read"]), reason_codes=["child.a"])
        b = core.allow_result(process_operation("git", argv=["git", "status"], effects=["process", "git_read"]), reason_codes=["child.b"])
        parent = compound_operation([a, b], effects=["process", "read"])
        result = core.compose_results([a, b], parent_operation=parent)
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertIn("composition.parent_effects_incomplete", result["uncertainties"])

    def test_parent_missing_child_target_downgrades_to_ask(self):
        t1 = target("/repo-a", "posix:dev1:ino20")
        t2 = target("/repo-b", "posix:dev1:ino21")
        a = core.allow_result(process_operation("pwd", path="/repo-a", object_id="posix:dev1:ino20", targets=[t1]), reason_codes=["child.a"])
        b = core.allow_result(process_operation("pwd", path="/repo-b", object_id="posix:dev1:ino21", targets=[t2]), reason_codes=["child.b"])
        parent = compound_operation([a, b], targets=[t1])
        result = core.compose_results([a, b], parent_operation=parent)
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertIn("composition.parent_targets_incomplete", result["uncertainties"])

    def test_parent_unknown_effect_downgrades_to_ask(self):
        a = core.allow_result(process_operation("pwd"), reason_codes=["child.a"])
        b = core.allow_result(process_operation("git", argv=["git", "status"], effects=["process", "read"]), reason_codes=["child.b"])
        parent = compound_operation([a, b], effects=["process", "read", "unknown_code_execution"])
        result = core.compose_results([a, b], parent_operation=parent)
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertIn("composition.parent_unknown", result["uncertainties"])

    def test_compound_parent_step_count_and_operators_are_bound(self):
        a = core.allow_result(process_operation("pwd"), reason_codes=["child.a"])
        b = core.allow_result(process_operation("git", argv=["git", "status"], effects=["process", "read"]), reason_codes=["child.b"])
        parent = compound_operation([a, b])
        parent["execution"]["operators"] = []
        result = core.compose_results([a, b], parent_operation=parent)
        self.assertEqual(result["decision"], "ASK_USER")
        self.assertEqual(result["uncertainties"], ["identity.parent_invalid"])


if __name__ == "__main__":
    unittest.main()

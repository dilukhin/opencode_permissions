"""Issue #59 A0: preserve the boundary until scoped reads are implemented.

All commands are data. The only executor records synthetic calls; YC is never
started. These tests do not prove IAM access, installed-shim behavior or restore.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "runtime" / "yc_guard"))

import build_yc_transitional_artifact as artifact  # noqa: E402
import classifier_yc  # noqa: E402
import yc_transitional_adapter as runtime  # noqa: E402

TRUSTED = {
    "invoked": "yc",
    "resolved_path": "C:/synthetic/yc.exe",
    "object_identity": "synthetic:yc-snapshot-boundary",
}


def fact(argv):
    return {
        "schema": "parsed-simple/v1",
        "platform": "windows",
        "parser": {"status": "exact", "profile": "synthetic-yc-snapshot-v1"},
        "executable": dict(TRUSTED),
        "argv": list(argv),
        "cwd": {"lexical": "C:/synthetic", "object_identity": "synthetic:cwd", "follow_mode": "target"},
        "targets": [],
        "redirects": [],
        "stdin": {"kind": "none"},
    }


class YcSnapshotBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((ROOT / "tests" / "yc_snapshot_boundary_cases.json").read_text(encoding="utf-8"))
        cls.cases = cls.corpus["cases"]

    def test_source_classifier_and_dispatch_obey_snapshot_corpus(self):
        self.assertEqual(self.corpus["execution_policy"], "parser_only_and_synthetic_executor")
        self.assertEqual(len({row["id"] for row in self.cases}), len(self.cases))
        for row in self.cases:
            with self.subTest(case=row["id"]):
                request = fact(row["argv"])
                classified = classifier_yc.analyze_yc(request)
                calls = []
                outcome = runtime.dispatch(
                    request, trusted_execution_target=TRUSTED,
                    executor=lambda path, tail: calls.append((path, tail)),
                )
                self.assertEqual(classified["decision"], row["expected_decision"])
                self.assertEqual(outcome["decision"], classified["decision"])
                self.assertEqual(outcome["execute"], row["expected_decision"] == "ALLOW")
                self.assertFalse(outcome["transitional_state_change_without_user_prompt"])
                if row["expected_decision"] == "ALLOW":
                    self.assertEqual(calls, [(TRUSTED["resolved_path"], row["argv"][1:])])
                    self.assertEqual(classified["reason_codes"], ["yc.policy.exact_read"])
                else:
                    self.assertEqual(calls, [])
                    self.assertIsNone(outcome["execution_result"])
                    reason = "yc.hard_deny" if row["expected_decision"] == "DENY" else "yc.policy.not_exact_allow"
                    self.assertEqual(classified["reason_codes"], [reason])

    def test_packaged_runtime_has_the_same_boundary_in_fresh_process(self):
        # A separate interpreter prevents source modules cached by other tests
        # from being mistaken for modules loaded from the materialized bundle.
        worker = '''
import json
from pathlib import Path
import sys
runtime_dir = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(runtime_dir))
import classifier_yc
import yc_transitional_adapter as runtime
assert Path(classifier_yc.__file__).resolve().parent == runtime_dir
assert classifier_yc.POLICY_PATH == runtime_dir.parent / "policy" / "yc" / "yc_policy.v1.json"
rows = []
for request in json.load(sys.stdin):
    calls = []
    result = runtime.dispatch(request, trusted_execution_target=request["executable"],
                              executor=lambda path, tail: calls.append([path, tail]))
    rows.append({"decision": result["decision"], "execute": result["execute"], "calls": calls})
print(json.dumps(rows))
'''
        with TemporaryDirectory() as td:
            bundle = Path(artifact.materialize(ROOT, output_root=Path(td))["artifact_dir"])
            self.assertEqual(artifact.validate_artifact(ROOT, bundle)["result"], "YC_TRANSITIONAL_ARTIFACT_VALID")
            completed = subprocess.run(
                [sys.executable, "-I", "-B", "-c", worker, str(bundle / "runtime")],
                input=json.dumps([fact(row["argv"]) for row in self.cases]),
                text=True, capture_output=True, check=True, timeout=30,
            )
        observed = json.loads(completed.stdout)
        self.assertEqual(len(observed), len(self.cases))
        for row, result in zip(self.cases, observed):
            with self.subTest(case=row["id"]):
                self.assertEqual(result["decision"], row["expected_decision"])
                allowed = row["expected_decision"] == "ALLOW"
                self.assertEqual(result["execute"], allowed)
                self.assertEqual(result["calls"], [[TRUSTED["resolved_path"], row["argv"][1:]]] if allowed else [])

    def test_caller_facts_do_not_create_resource_provenance(self):
        claims = (
            {"trusted": True, "approved": True},
            {"owner_id": "synthetic-owner", "folder_id": "synthetic-folder"},
            {"source_disk_id": "synthetic-disk", "vm_id": "synthetic-vm", "status": "READY"},
            {"resource_binding": {"verified": True, "snapshot_id": "synthetic-snapshot"}},
            {"targets": [{"role": "cloud_resource", "kind": "cloud_resource", "identity": {
                "provider": "yandex-cloud", "resource_id": "synthetic-snapshot", "trusted": True,
            }}]},
        )
        for resource in ("disk", "snapshot"):
            for claim in claims:
                with self.subTest(resource=resource, claim=claim):
                    request = fact(["yc", "compute", resource, "get", "--id", "synthetic-" + resource])
                    request.update(copy.deepcopy(claim))
                    calls = []
                    outcome = runtime.dispatch(
                        request, trusted_execution_target=TRUSTED,
                        executor=lambda *args: calls.append(args),
                        caller_context={"evidence_source": "owner_console", "status": "READY"},
                    )
                    self.assertEqual(outcome["decision"], "ASK_USER")
                    self.assertFalse(outcome["execute"])
                    self.assertEqual(calls, [])

    def test_every_caller_approval_key_is_rejected_before_dispatch(self):
        for key in ("approved", "approval", "authorized", "authorization", "policy_allow", "skip_guard", "bypass"):
            for value in (True, False, "synthetic-receipt"):
                with self.subTest(key=key, value=value):
                    calls = []
                    with self.assertRaises(runtime.YcRuntimeContractError) as ctx:
                        runtime.dispatch(
                            fact(["yc", "compute", "snapshot", "delete", "--id", "synthetic-snapshot"]),
                            trusted_execution_target=TRUSTED,
                            executor=lambda *args: calls.append(args), caller_context={key: value},
                        )
                    self.assertEqual(ctx.exception.code, "CALLER_APPROVAL_NOT_TRUSTED")
                    self.assertEqual(calls, [])

    def test_only_existing_pinned_vm_lifecycle_has_mutation_exception(self):
        mutations = classifier_yc.load_policy()["allow_mutations"]
        self.assertEqual(len(mutations), 2)
        self.assertEqual({row["action"] for row in mutations}, {"start", "stop"})
        self.assertEqual(len({row["resource_id"] for row in mutations}), 1)
        for row in mutations:
            with self.subTest(action=row["action"]):
                self.assertEqual((row["service"], row["resource"]), ("compute", "instance"))
                self.assertEqual(row["argv"], ["yc", "compute", "instance", row["action"], "--id", row["resource_id"]])
                calls = []
                outcome = runtime.dispatch(
                    fact(row["argv"]), trusted_execution_target=TRUSTED,
                    executor=lambda path, tail: calls.append((path, tail)),
                )
                self.assertEqual(outcome["decision"], "ALLOW")
                self.assertTrue(outcome["transitional_state_change_without_user_prompt"])
                self.assertEqual(calls, [(TRUSTED["resolved_path"], row["argv"][1:])])


if __name__ == "__main__":
    unittest.main()

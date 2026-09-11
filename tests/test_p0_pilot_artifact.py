import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import build_p0_pilot_artifact as artifact  # noqa: E402


class P0PilotArtifactPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = artifact.build_plan(ROOT)

    def test_plan_is_exact_current_runtime_revalidated_target(self):
        registry = json.loads((ROOT / "tests" / "compatibility" / "registry.json").read_text(encoding="utf-8"))
        manifest = self.plan["manifest"]
        self.assertEqual(manifest["target"]["exact_version"], registry["current_target"])
        self.assertEqual(manifest["target"]["platform"], "linux")
        self.assertTrue(manifest["constraints"]["exact_version_only"])
        self.assertFalse(manifest["constraints"]["nearest_version_fallback"])
        self.assertTrue(manifest["constraints"]["requires_deployable_profile"])

    def test_allow_surface_is_only_single_file_grep(self):
        profile = self.plan["runtime_profile"]
        self.assertEqual(profile["allow_families"], ["grep.single_nonsecret_workspace_file"])
        self.assertFalse(profile["constraints"]["find"])
        self.assertFalse(profile["constraints"]["git"])
        self.assertFalse(profile["constraints"]["pipelines"])
        self.assertFalse(profile["constraints"]["compound_shell"])
        self.assertFalse(profile["constraints"]["build_test_static_check"])
        self.assertFalse(profile["constraints"]["state_changing"])
        self.assertFalse(profile["constraints"]["remote"])
        self.assertFalse(profile["constraints"]["auditor"])
        self.assertFalse(profile["constraints"]["workspace_trust"])

    def test_secret_boundary_is_resolved_from_canonical_native_policy(self):
        profile = self.plan["runtime_profile"]
        rules = profile["secret_boundary"]["resolved_rules"]
        self.assertGreater(len(rules), 0)
        self.assertTrue(all(row["id"].startswith("read.secret") for row in rules))
        self.assertEqual({row["action"] for row in rules}, {"ask", "deny"})

    def test_metrics_contract_is_ask_path_privacy_safe_and_allow_gated(self):
        metrics = self.plan["runtime_profile"]["metrics"]
        self.assertEqual(metrics["schema"], "opencode-permissions-p0-metrics/v1")
        self.assertEqual(metrics["scope"], "ask_path")
        self.assertTrue(metrics["required_for_classifier_allow"])
        self.assertEqual(metrics["storage"], "per_process_aggregate_snapshot")
        self.assertEqual(metrics["state_resolution"], "os_homedir_local_state")
        self.assertFalse(metrics["raw_inputs"])
        self.assertEqual(metrics["max_reason_buckets"], 64)
        self.assertEqual(
            metrics["counters"],
            [
                "native_ask",
                "classifier_allow",
                "classifier_deny",
                "residual_ask",
                "classifier_error/fail_closed",
                "binding_reject",
            ],
        )
        self.assertNotIn("native_allow", metrics["counters"])
        self.assertNotIn("native_deny", metrics["counters"])

    def test_bundle_files_are_sha256_bound_and_checkout_independent(self):
        manifest = self.plan["manifest"]
        expected = {
            "bridge.js",
            "profile.json",
            "runtime/opencode_p0_adapter.py",
            "runtime/classifier_analyzers.py",
            "runtime/classifier_core.py",
            "runtime/normalized_operation_identity.py",
        }
        self.assertEqual({item["path"] for item in manifest["files"]}, expected)
        for item in manifest["files"]:
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(item["size"], 0)
        self.assertFalse(manifest["constraints"]["developer_checkout_dependency"])
        self.assertTrue(manifest["constraints"]["managed_global_plugin_required"])
        self.assertFalse(manifest["constraints"]["setup_semantic_rewrite"])

    def test_byte_bound_sources_and_pilot_output_are_lf_pinned(self):
        paths = [*artifact.BUNDLE_SOURCES.values(), "dist/pilot/sha256-test/manifest.json"]
        completed = subprocess.run(
            ["git", "check-attr", "eol", "--", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        observed = {}
        for line in completed.stdout.splitlines():
            path, attribute, value = line.rsplit(": ", 2)
            self.assertEqual(attribute, "eol")
            observed[path] = value
        self.assertEqual(set(observed), set(paths))
        self.assertTrue(all(value == "lf" for value in observed.values()))

    def test_minimal_bundle_imports_without_yc_module_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = Path(temporary)
            runtime = isolated / "runtime"
            runtime.mkdir()
            for relative_path, payload in self.plan["payloads"].items():
                if relative_path == "profile.json" or not relative_path.startswith("runtime/"):
                    continue
                destination = isolated / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)

            self.assertFalse((runtime / "classifier_yc.py").exists())
            probe = textwrap.dedent(
                """
import json
from opencode_p0_adapter import prepare
from classifier_analyzers import analyze_simple

fact = {
    "schema": "parsed-simple/v1",
    "platform": "linux",
    "parser": {"status": "exact", "profile": "synthetic"},
    "executable": {
        "invoked": "yc",
        "resolved_path": "/usr/bin/yc",
        "object_identity": "synthetic:yc",
    },
    "argv": ["yc", "compute", "instance", "start"],
    "cwd": {
        "lexical": "/repo",
        "object_identity": "synthetic:cwd",
        "follow_mode": "target",
        "boundary": "workspace",
    },
    "targets": [],
    "redirects": [],
    "stdin": {"kind": "none"},
}
import_result = analyze_simple(fact)
print(json.dumps({"imported": True, "result": import_result}, sort_keys=True))
                """
            ).replace("\n    ", "\n")
            completed = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=isolated,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(runtime)},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["imported"])
            self.assertEqual(payload["result"]["decision"], "ASK_USER")
            self.assertIn("yc.analyzer_unavailable", payload["result"]["reason_codes"])
            self.assertIn("process", payload["result"]["effects"])
            self.assertIn("network", payload["result"]["effects"])
            self.assertIn("unknown", payload["result"]["effects"])

    def test_manifest_disables_deferred_or_state_changing_components(self):
        constraints = self.plan["manifest"]["constraints"]
        self.assertFalse(constraints["auditor_enabled"])
        self.assertFalse(constraints["workspace_trust_enabled"])
        self.assertFalse(constraints["state_changing_classifier_enabled"])
        self.assertEqual(constraints["classifier_error_result"], "ASK_USER")
        self.assertEqual(constraints["competing_effective_layer_result"], "CONFLICT")

    def test_production_bridge_contains_no_dc4_fixture_or_project_local_dependency(self):
        source = (ROOT / "runtime" / "p0" / "opencode-permissions.js").read_text(encoding="utf-8")
        forbidden = [
            "DC4_SCENARIO",
            "mock_provider",
            "DC4_EXPECT_SENTINEL",
            ".opencode/plugins",
            "repoRoot",
            "DC4_REPO_ROOT",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, source)
        self.assertIn('import.meta.url', source)
        self.assertIn('manifest.json', source)
        self.assertNotIn('client.global.health()', source)
        self.assertIn('spawnSync(process.execPath, ["--version"]', source)
        self.assertIn('env: {}', source)
        self.assertIn('versionValue === bundle.manifest.target.exact_version', source)
        self.assertIn('path.basename(root) !== manifest.artifact_path_segment', source)
        self.assertIn('input.cwd !== state.cwd', source)
        self.assertIn('["--command", state.command, "--cwd", input.cwd, "--workspace-root", directory]', source)
        self.assertIn('"once"', source)
        self.assertIn('"reject"', source)

    def test_production_bridge_metrics_are_bounded_and_fail_closed_before_execution(self):
        source = (ROOT / "runtime" / "p0" / "opencode-permissions.js").read_text(encoding="utf-8")
        self.assertIn('const MAX_BUCKETS = 64', source)
        self.assertIn('recordMetric(bundle, "native_ask")', source)
        self.assertIn('recordMetric(bundle, "classifier_allow"', source)
        self.assertIn('throw new Error("P0_METRICS_WRITE_FAILED")', source)
        self.assertIn('fs.fsyncSync(descriptor)', source)
        self.assertIn('fs.renameSync(temporary, destination)', source)
        self.assertIn('raw_inputs', (ROOT / "pilot" / "p0" / "profile.v1.json").read_text(encoding="utf-8"))
        self.assertNotIn('process.env.XDG_STATE_HOME', source)
        self.assertNotIn('native_allow",', source)
        self.assertNotIn('native_deny",', source)

    @unittest.skipUnless(sys.platform == "linux", "P0 committed artifact is Linux-only")
    def test_committed_artifact_is_exact_materialization_of_current_plan(self):
        result = artifact.validate_committed_artifact(ROOT)
        self.assertEqual(result["result"], "MP0_ARTIFACT_VALID")
        self.assertEqual(result["artifact_id"], self.plan["artifact_id"])
        self.assertEqual(result["artifact_path"], self.plan["artifact_path"])
        self.assertEqual(result["opencode_version"], self.plan["manifest"]["target"]["exact_version"])

    def test_print_plan_for_review_and_artifact_materialization(self):
        public = {
            "artifact_id": self.plan["artifact_id"],
            "artifact_path": self.plan["artifact_path"],
            "manifest": self.plan["manifest"],
            "runtime_profile": self.plan["runtime_profile"],
        }
        print("P0_PILOT_PLAN_JSON=" + json.dumps(public, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

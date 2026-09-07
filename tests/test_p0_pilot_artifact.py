import json
from pathlib import Path
import sys
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

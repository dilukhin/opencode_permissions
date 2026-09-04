from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "tests" / "dc4_runtime" / "dc4_plugin.js"


class DC4EnvironmentDependencyContractTests(unittest.TestCase):
    def test_plugin_does_not_snapshot_entire_process_environment(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertNotIn("Object.entries(process.env)", source)
        self.assertNotIn("snapshotEnv()", source)
        self.assertNotIn("sameEnv(", source)

    def test_plugin_uses_explicit_declared_dependency(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertIn('const declaredEnvDependencies = ["OPENCODE_PERMISSIONS_DC4_AUTHZ_DEP"]', source)
        self.assertIn("snapshotDeclaredEnv()", source)
        self.assertIn("sameDeclaredEnv", source)

    def test_post_authorization_shell_env_injection_remains_fail_closed(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("Object.keys(output?.env || {}).length !== 0", source)
        self.assertIn('reason: "environment_drift"', source)
        self.assertIn("DC4_ENVIRONMENT_DRIFT", source)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
COMPAT = TESTS / "compatibility"
REGISTRY = COMPAT / "registry.json"
CONTRACT = TESTS / "artifact_contract" / "artifact_contract.py"

spec = importlib.util.spec_from_file_location("artifact_contract", CONTRACT)
contract = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(contract)


class CurrentCompatibilityArtifactTests(unittest.TestCase):
    def test_current_linux_deployable_profile_has_valid_exact_artifact(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        version = registry["current_target"]
        profile = json.loads((COMPAT / registry["profiles"][version]).read_text(encoding="utf-8"))

        self.assertTrue(profile["deployable"])
        self.assertIn("linux", profile["deployable_platforms"])
        artifact_id = profile["policy_artifacts"]["linux"]
        segment = contract.artifact_path_segment(artifact_id)
        artifact_dir = ROOT / "dist" / "opencode" / segment
        manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))

        result = contract.validate_contract(
            manifest,
            profile,
            version,
            ROOT,
            artifact_dir,
            installed_platform="linux",
        )
        self.assertEqual(result["result"], "VALID_DEPLOYABLE_ARTIFACT_CONTRACT")
        self.assertEqual(result["artifact_id"], artifact_id)
        self.assertEqual(result["exact_version"], version)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools" / "render_native_policy.py"
CONTRACT = ROOT / "tests" / "artifact_contract" / "artifact_contract.py"
CANDIDATE = ROOT / "tests" / "native_policy" / "policy_candidate.json"
CANONICAL = ROOT / "policy" / "native" / "rules.v1.json"
PROFILE = ROOT / "tests" / "compatibility" / "profiles" / "opencode-1.18.26.json"
ARTIFACT_SEGMENT = "sha256-d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508"
ARTIFACT_DIR = ROOT / "dist" / "opencode" / ARTIFACT_SEGMENT
MANIFEST = ARTIFACT_DIR / "manifest.json"
OUTPUT = ARTIFACT_DIR / "permission.jsonc"

rspec = importlib.util.spec_from_file_location("render_native_policy", RENDERER)
renderer = importlib.util.module_from_spec(rspec)
assert rspec.loader is not None
rspec.loader.exec_module(renderer)

cspec = importlib.util.spec_from_file_location("artifact_contract", CONTRACT)
contract = importlib.util.module_from_spec(cspec)
assert cspec.loader is not None
cspec.loader.exec_module(contract)


class GateBPromotedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        cls.canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
        cls.profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_canonical_source_is_exact_promotion(self):
        expected = renderer.promote_candidate(self.candidate)
        self.assertEqual(self.canonical, expected)

    def test_committed_output_is_exact_renderer_output(self):
        self.assertEqual(OUTPUT.read_bytes(), renderer.render_bytes(self.canonical))

    def test_manifest_digests_and_identity_match_committed_bytes(self):
        self.assertEqual(
            self.manifest["policy_source"]["sha256"],
            contract.sha256_file(CANONICAL),
        )
        self.assertEqual(
            self.manifest["output"]["sha256"],
            contract.sha256_file(OUTPUT),
        )
        self.assertEqual(
            self.manifest["artifact_id"],
            contract.compute_artifact_id(self.manifest),
        )
        self.assertEqual(
            self.manifest["artifact_path_segment"],
            contract.artifact_path_segment(self.manifest["artifact_id"]),
        )
        self.assertEqual(ARTIFACT_DIR.name, self.manifest["artifact_path_segment"])

    def test_exact_linux_deployable_contract(self):
        result = contract.validate_contract(
            self.manifest,
            self.profile,
            "1.18.26",
            ROOT,
            ARTIFACT_DIR,
            installed_platform="linux",
        )
        self.assertEqual(result["result"], "VALID_DEPLOYABLE_ARTIFACT_CONTRACT")

    def test_windows_is_not_deployable_from_current_profile(self):
        self.assertNotIn("windows", self.profile["deployable_platforms"])
        self.assertEqual(self.profile["platform_status"]["windows"], "SOURCE_REVALIDATED")


if __name__ == "__main__":
    unittest.main()

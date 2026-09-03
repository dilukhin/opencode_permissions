import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
MODULE = ROOT / "artifact_contract" / "artifact_contract.py"
CURRENT_PROFILE = ROOT / "compatibility" / "profiles" / "opencode-1.18.26.json"

spec = importlib.util.spec_from_file_location("artifact_contract", MODULE)
contract = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(contract)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GateBArtifactContractTests(unittest.TestCase):
    def setUp(self):
        self.current_profile = json.loads(CURRENT_PROFILE.read_text(encoding="utf-8"))

    def make_fixture(self, td):
        root = Path(td)
        source = root / "source" / "policy" / "native" / "rules.v1.json"
        staging = root / "staging-permission.jsonc"
        source.parent.mkdir(parents=True)
        source.write_text('{"rules":[["fallback","*","*","ask"]]}\n', encoding="utf-8")
        staging.write_text('{"permission":{"*":"ask"}}\n', encoding="utf-8")

        profile = copy.deepcopy(self.current_profile)
        profile["deployable"] = True
        profile["deployable_platforms"] = ["linux"]
        profile["blocking_reasons"] = []

        manifest = {
            "schema": 1,
            "artifact_format": "opencode-permission-artifact/v1",
            "artifact_id": "",
            "artifact_path_segment": "",
            "status": "deployable",
            "owner": "dilukhin/opencode_permissions",
            "target": {
                "product": "opencode",
                "exact_version": "1.18.26",
                "platform": "linux",
                "compatibility_profile_id": profile["profile_id"],
            },
            "policy_source": {"path": "policy/native/rules.v1.json", "sha256": digest(source)},
            "renderer": {"id": "opencode-v1-permission-renderer", "version": 1},
            "output": {"relative_path": "permission.jsonc", "sha256": digest(staging)},
            "constraints": {
                "exact_version_only": True,
                "requires_deployable_profile": True,
                "nearest_version_fallback": False,
                "setup_semantic_rewrite": False,
                "effective_readback_required": True,
                "competing_effective_layer_result": "CONFLICT",
            },
        }
        manifest["artifact_id"] = contract.compute_artifact_id(manifest)
        manifest["artifact_path_segment"] = contract.artifact_path_segment(manifest["artifact_id"])
        profile["policy_artifacts"] = {"linux": manifest["artifact_id"]}
        artifact_dir = root / "artifacts" / manifest["artifact_path_segment"]
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "permission.jsonc").write_bytes(staging.read_bytes())
        return root, profile, manifest, source, artifact_dir

    def assert_error(self, expected, manifest, profile, root, artifact_dir, installed_platform="linux"):
        with self.assertRaises(contract.ArtifactContractError) as ctx:
            contract.validate_contract(manifest, profile, "1.18.26", root / "source", artifact_dir, installed_platform=installed_platform)
        self.assertEqual(ctx.exception.code, expected)

    def test_synthetic_valid_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            result = contract.validate_contract(manifest, profile, "1.18.26", root / "source", artifact_dir, installed_platform="linux")
            self.assertEqual(result["result"], "VALID_DEPLOYABLE_ARTIFACT_CONTRACT")
            self.assertEqual(result["platform"], "linux")
            self.assertEqual(result["artifact_path_segment"], manifest["artifact_path_segment"])

    def test_installed_version_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            with self.assertRaises(contract.ArtifactContractError) as ctx:
                contract.validate_contract(manifest, profile, "1.18.27", root / "source", artifact_dir, installed_platform="linux")
            self.assertEqual(ctx.exception.code, "INSTALLED_VERSION_MISMATCH")

    def test_installed_platform_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            with self.assertRaises(contract.ArtifactContractError) as ctx:
                contract.validate_contract(manifest, profile, "1.18.26", root / "source", artifact_dir)
            self.assertEqual(ctx.exception.code, "INSTALLED_PLATFORM_REQUIRED")

    def test_installed_platform_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            self.assert_error("INSTALLED_PLATFORM_MISMATCH", manifest, profile, root, artifact_dir, installed_platform="windows")

    def test_profile_platform_scope_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["target"]["platform"] = "windows"
            manifest["artifact_id"] = contract.compute_artifact_id(manifest)
            manifest["artifact_path_segment"] = contract.artifact_path_segment(manifest["artifact_id"])
            profile["policy_artifacts"] = {"linux": manifest["artifact_id"]}
            new_dir = artifact_dir.parent / manifest["artifact_path_segment"]
            new_dir.mkdir()
            (new_dir / "permission.jsonc").write_bytes((artifact_dir / "permission.jsonc").read_bytes())
            self.assert_error("PROFILE_NOT_DEPLOYABLE_FOR_PLATFORM", manifest, profile, root, new_dir, installed_platform="windows")

    def test_profile_artifact_pin_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            profile["policy_artifacts"]["linux"] = "sha256:" + "0" * 64
            self.assert_error("PROFILE_ARTIFACT_ID_MISMATCH", manifest, profile, root, artifact_dir)

    def test_artifact_path_segment_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["artifact_path_segment"] = "sha256-" + "0" * 64
            self.assert_error("ARTIFACT_PATH_SEGMENT_MISMATCH", manifest, profile, root, artifact_dir)

    def test_artifact_directory_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            wrong = artifact_dir.parent / "wrong-directory"
            wrong.mkdir()
            (wrong / "permission.jsonc").write_bytes((artifact_dir / "permission.jsonc").read_bytes())
            self.assert_error("ARTIFACT_DIRECTORY_MISMATCH", manifest, profile, root, wrong)

    def test_output_digest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            (artifact_dir / "permission.jsonc").write_text("changed\n", encoding="utf-8")
            self.assert_error("ARTIFACT_OUTPUT_DIGEST_MISMATCH", manifest, profile, root, artifact_dir)

    def test_source_digest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, source, artifact_dir = self.make_fixture(td)
            source.write_text("changed\n", encoding="utf-8")
            self.assert_error("POLICY_SOURCE_DIGEST_MISMATCH", manifest, profile, root, artifact_dir)

    def test_artifact_id_binds_identity_core(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["renderer"]["version"] = 2
            self.assert_error("ARTIFACT_ID_MISMATCH", manifest, profile, root, artifact_dir)

    def test_setup_semantic_rewrite_is_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["constraints"]["setup_semantic_rewrite"] = True
            self.assert_error("SETUP_SEMANTIC_REWRITE_FORBIDDEN", manifest, profile, root, artifact_dir)

    def test_effective_readback_is_mandatory(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["constraints"]["effective_readback_required"] = False
            self.assert_error("EFFECTIVE_READBACK_REQUIRED", manifest, profile, root, artifact_dir)

    def test_nearest_version_fallback_is_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["constraints"]["nearest_version_fallback"] = True
            self.assert_error("NEAREST_VERSION_FALLBACK_FORBIDDEN", manifest, profile, root, artifact_dir)

    def test_competing_layer_must_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, artifact_dir = self.make_fixture(td)
            manifest["constraints"]["competing_effective_layer_result"] = "MERGE"
            self.assert_error("COMPETING_LAYER_MUST_CONFLICT", manifest, profile, root, artifact_dir)


if __name__ == "__main__":
    unittest.main()

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
        output = root / "artifact" / "permission.jsonc"
        source.parent.mkdir(parents=True)
        output.parent.mkdir(parents=True)
        source.write_text('{"rules":[["fallback","*","*","ask"]]}\n', encoding="utf-8")
        output.write_text('{"permission":{"*":"ask"}}\n', encoding="utf-8")

        profile = copy.deepcopy(self.current_profile)
        profile["deployable"] = True
        profile["deployable_platforms"] = ["linux"]
        profile["policy_artifact_id"] = "synthetic-bound-by-manifest"
        profile["blocking_reasons"] = []

        manifest = {
            "schema": 1,
            "artifact_format": "opencode-permission-artifact/v1",
            "artifact_id": "",
            "status": "deployable",
            "owner": "dilukhin/opencode_permissions",
            "target": {
                "product": "opencode",
                "exact_version": "1.18.26",
                "platform": "linux",
                "compatibility_profile_id": profile["profile_id"],
            },
            "policy_source": {
                "path": "policy/native/rules.v1.json",
                "sha256": digest(source),
            },
            "renderer": {
                "id": "opencode-v1-permission-renderer",
                "version": 1,
            },
            "output": {
                "relative_path": "permission.jsonc",
                "sha256": digest(output),
            },
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
        return root, profile, manifest, source, output

    def assert_error(self, expected, manifest, profile, root, installed_platform="linux"):
        with self.assertRaises(contract.ArtifactContractError) as ctx:
            contract.validate_contract(
                manifest,
                profile,
                "1.18.26",
                root / "source",
                root / "artifact",
                installed_platform=installed_platform,
            )
        self.assertEqual(ctx.exception.code, expected)

    def test_synthetic_valid_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            result = contract.validate_contract(
                manifest,
                profile,
                "1.18.26",
                root / "source",
                root / "artifact",
                installed_platform="linux",
            )
            self.assertEqual(result["result"], "VALID_DEPLOYABLE_ARTIFACT_CONTRACT")
            self.assertEqual(result["platform"], "linux")

    def test_current_profile_cannot_deploy(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, manifest, _, _ = self.make_fixture(td)
            self.assert_error("PROFILE_NOT_DEPLOYABLE", manifest, self.current_profile, root)

    def test_installed_version_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            with self.assertRaises(contract.ArtifactContractError) as ctx:
                contract.validate_contract(
                    manifest,
                    profile,
                    "1.18.27",
                    root / "source",
                    root / "artifact",
                    installed_platform="linux",
                )
            self.assertEqual(ctx.exception.code, "INSTALLED_VERSION_MISMATCH")

    def test_installed_platform_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            with self.assertRaises(contract.ArtifactContractError) as ctx:
                contract.validate_contract(
                    manifest,
                    profile,
                    "1.18.26",
                    root / "source",
                    root / "artifact",
                )
            self.assertEqual(ctx.exception.code, "INSTALLED_PLATFORM_REQUIRED")

    def test_installed_platform_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            self.assert_error("INSTALLED_PLATFORM_MISMATCH", manifest, profile, root, installed_platform="windows")

    def test_profile_platform_scope_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            manifest["target"]["platform"] = "windows"
            manifest["artifact_id"] = contract.compute_artifact_id(manifest)
            self.assert_error("PROFILE_NOT_DEPLOYABLE_FOR_PLATFORM", manifest, profile, root, installed_platform="windows")

    def test_output_digest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, output = self.make_fixture(td)
            output.write_text("changed\n", encoding="utf-8")
            self.assert_error("ARTIFACT_OUTPUT_DIGEST_MISMATCH", manifest, profile, root)

    def test_source_digest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, source, _ = self.make_fixture(td)
            source.write_text("changed\n", encoding="utf-8")
            self.assert_error("POLICY_SOURCE_DIGEST_MISMATCH", manifest, profile, root)

    def test_artifact_id_binds_identity_core(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            manifest["renderer"]["version"] = 2
            self.assert_error("ARTIFACT_ID_MISMATCH", manifest, profile, root)

    def test_setup_semantic_rewrite_is_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            manifest["constraints"]["setup_semantic_rewrite"] = True
            self.assert_error("SETUP_SEMANTIC_REWRITE_FORBIDDEN", manifest, profile, root)

    def test_effective_readback_is_mandatory(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            manifest["constraints"]["effective_readback_required"] = False
            self.assert_error("EFFECTIVE_READBACK_REQUIRED", manifest, profile, root)

    def test_nearest_version_fallback_is_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            manifest["constraints"]["nearest_version_fallback"] = True
            self.assert_error("NEAREST_VERSION_FALLBACK_FORBIDDEN", manifest, profile, root)

    def test_competing_layer_must_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root, profile, manifest, _, _ = self.make_fixture(td)
            manifest["constraints"]["competing_effective_layer_result"] = "MERGE"
            self.assert_error("COMPETING_LAYER_MUST_CONFLICT", manifest, profile, root)


if __name__ == "__main__":
    unittest.main()

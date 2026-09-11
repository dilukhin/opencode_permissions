import hashlib
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_yc_transitional_artifact as artifact  # noqa: E402


class YcTransitionalArtifactTests(unittest.TestCase):
    def test_plan_is_content_bound_and_uses_canonical_policy(self):
        left = artifact.build_plan(ROOT)
        right = artifact.build_plan(ROOT)
        self.assertEqual(left["artifact_id"], right["artifact_id"])
        self.assertRegex(left["artifact_id"], r"^sha256:[0-9a-f]{64}$")
        manifest = left["manifest"]
        self.assertEqual(manifest["policy"]["schema"], "yc-policy/v1")
        policy_bytes = (ROOT / "policy" / "yc" / "yc_policy.v1.json").read_bytes()
        self.assertEqual(manifest["policy"]["sha256"], hashlib.sha256(policy_bytes).hexdigest())
        self.assertTrue(manifest["constraints"]["canonical_policy_only"])
        self.assertFalse(manifest["constraints"]["setup_semantic_rewrite"])
        self.assertFalse(manifest["constraints"]["runtime_path_resolution"])
        self.assertFalse(manifest["constraints"]["caller_approval_flags_trusted"])
        self.assertTrue(manifest["constraints"]["transitional_exact_mutation_auto_allow"])
        self.assertFalse(manifest["constraints"]["full_authorization_binding_complete"])

    def test_exact_transitional_mutations_are_derived_from_policy(self):
        plan = artifact.build_plan(ROOT)
        policy = json.loads((ROOT / "policy" / "yc" / "yc_policy.v1.json").read_text(encoding="utf-8"))
        expected = [
            {
                "service": row.get("service"),
                "resource": row.get("resource"),
                "action": row.get("action"),
                "resource_id": row["resource_id"],
                "argv": row["argv"],
            }
            for row in policy["allow_mutations"]
        ]
        self.assertEqual(plan["manifest"]["transitional_auto_allow_mutations"], expected)

    def test_materialize_and_validate_without_repository_write(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            written = artifact.materialize(ROOT, output_root=out)
            artifact_dir = Path(written["artifact_dir"])
            self.assertTrue((artifact_dir / "manifest.json").is_file())
            self.assertEqual(
                artifact.validate_artifact(ROOT, artifact_dir)["result"],
                "YC_TRANSITIONAL_ARTIFACT_VALID",
            )

    def test_tampered_payload_fails_closed(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            artifact_dir = Path(artifact.materialize(ROOT, output_root=out)["artifact_dir"])
            policy_path = artifact_dir / "policy" / "yc" / "yc_policy.v1.json"
            policy_path.write_bytes(policy_path.read_bytes() + b"\n")
            with self.assertRaises(artifact.YcArtifactError) as ctx:
                artifact.validate_artifact(ROOT, artifact_dir)
            self.assertIn(
                ctx.exception.code,
                {"YC_ARTIFACT_FILE_SIZE_MISMATCH", "YC_ARTIFACT_FILE_DIGEST_MISMATCH", "YC_ARTIFACT_FILE_CONTENT_MISMATCH"},
            )

    def test_adapter_content_change_changes_artifact_identity(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            for dest, source in artifact.BUNDLE_SOURCES.items():
                target = temp_root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, target)
            before = artifact.build_plan(temp_root)["artifact_id"]
            adapter_path = temp_root / "runtime" / "yc_guard" / "yc_transitional_adapter.py"
            adapter_path.write_text(adapter_path.read_text(encoding="utf-8") + "\n# synthetic change\n", encoding="utf-8")
            after = artifact.build_plan(temp_root)["artifact_id"]
            self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()

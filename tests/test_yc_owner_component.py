import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("owner_component", ROOT / "tools/build_yc_owner_component.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class OwnerComponentTests(unittest.TestCase):
    def test_repeatable_identity_and_inactive_boundary(self):
        first, second = builder.plan(ROOT), builder.plan(ROOT)
        self.assertEqual(first, second)
        self.assertFalse(first["manifest"]["execution_enabled"])
        self.assertEqual(len(first["payloads"]), 16)
        self.assertNotIn(b"def main(", first["payloads"]["runtime/approval_owner/ledger.py"])

    def test_exact_materialization_and_tampered_payload_or_manifest_refused(self):
        for relative in ("manifest.json", "runtime/approval_owner/ledger.py"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp) / "component"
                manifest = builder.materialize(ROOT, destination)
                self.assertEqual(builder.validate(ROOT, destination), manifest)
                path = destination / relative
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(builder.ComponentError):
                    builder.validate(ROOT, destination)

    def test_extra_files_and_existing_output_cannot_be_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "component"
            builder.materialize(ROOT, destination)
            (destination / "runtime/unreviewed.py").write_text("raise RuntimeError('must not import')")
            with self.assertRaises(builder.ComponentError):
                builder.validate(ROOT, destination)
            with self.assertRaises(builder.ComponentError):
                builder.materialize(ROOT, destination)

    def test_no_setup_rewrite_or_deployment_flag_outside_identity(self):
        manifest = builder.plan(ROOT)["manifest"]
        core = {k: v for k, v in manifest.items() if k != "artifact_id"}
        self.assertEqual(builder.identity(core), manifest["artifact_id"])
        core["execution_enabled"] = True
        self.assertNotEqual(builder.identity(core), manifest["artifact_id"])

    def test_explicit_candidate_is_distinct_and_cannot_be_adopted_as_library(self):
        ref = '1f7d89d9a8cd2352c6df865e8915f66171475972'
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'candidate'
            candidate = builder.materialize(ROOT, output, source_ref=ref)
            self.assertTrue(candidate['execution_enabled'])
            self.assertEqual(candidate['source_ref'], ref)
            self.assertFalse(candidate['installed_acceptance'])
            self.assertNotEqual(candidate['artifact_id'], builder.plan(ROOT)['manifest']['artifact_id'])
            with self.assertRaises(builder.ComponentError):
                builder.validate(ROOT, output)
            self.assertEqual(builder.validate(ROOT, output, source_ref=ref), candidate)
        for ref in ('main', '', 'HEAD', '0' * 39):
            with self.assertRaises(builder.ComponentError):
                builder.plan(ROOT, source_ref=ref)

    def test_published_candidate_is_exact_authoritative_output(self):
        ref = '1f7d89d9a8cd2352c6df865e8915f66171475972'
        candidate = builder.plan(ROOT, source_ref=ref)['manifest']
        path = ROOT / 'dist/yc_owner' / candidate['artifact_id'].replace(':','-',1) / 'manifest.json'
        self.assertEqual(path.read_bytes(), builder.canonical(candidate) + b'\n')


if __name__ == "__main__":
    unittest.main()

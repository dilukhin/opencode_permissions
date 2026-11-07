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
        self.assertEqual(len(first["payloads"]), 7)
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


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "stage0_inventory.py"
spec = importlib.util.spec_from_file_location("stage0_inventory", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class Stage0InventoryTests(unittest.TestCase):
    def test_extract_permission_view_drops_provider_data(self):
        cfg = {
            "provider": {"x": {"apiKey": "SECRET"}},
            "permission": {"bash": "ask"},
            "default_agent": "build",
            "agent": {
                "build": {
                    "mode": "primary",
                    "permission": {"edit": "allow"},
                    "model": "provider/model",
                }
            },
        }
        view = mod.extract_permission_view(cfg)
        self.assertEqual(
            view,
            {
                "permission": {"bash": "ask"},
                "default_agent": "build",
                "agent": {"build": {"permission": {"edit": "allow"}, "mode": "primary"}},
            },
        )
        self.assertNotIn("SECRET", json.dumps(view))
        self.assertNotIn("provider", view)

    def test_extract_v2_permissions(self):
        cfg = {
            "permissions": [{"action": "shell", "resource": "git status *", "effect": "allow"}],
            "agent": {"review": {"permissions": [{"action": "edit", "resource": "*", "effect": "deny"}]}},
        }
        view = mod.extract_permission_view(cfg)
        self.assertIn("permissions", view)
        self.assertIn("agent", view)

    def test_safe_file_meta_uses_metadata_without_content(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "opencode.json"
            p.write_text('{"provider":{"apiKey":"SECRET"}}', encoding="utf-8")
            meta = mod.safe_file_meta(p)
            self.assertTrue(meta["exists"])
            self.assertIn("size", meta)
            self.assertIn("mtime_ns", meta)
            self.assertNotIn("content", meta)
            self.assertNotIn("SECRET", json.dumps(meta))

    def test_resolved_probe_skips_without_pure(self):
        result = mod.resolved_permission_probe("opencode", Path.cwd(), {"supports_pure": False})
        self.assertEqual(result["status"], "skipped")
        self.assertIn("--pure", result["reason"])

    def test_permission_corpus_manifest_and_unique_ids(self):
        base = Path(__file__).resolve().parent / "permission_cases"
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        ids = []
        for name in manifest["case_files"]:
            payload = json.loads((base / name).read_text(encoding="utf-8"))
            self.assertEqual(payload["case_count"], len(payload["cases"]))
            for case in payload["cases"]:
                for key in ("id", "category", "request", "expected_decision", "expected_effects", "execution_policy"):
                    self.assertIn(key, case)
                ids.append(case["id"])
        self.assertEqual(manifest["total_cases"], len(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(49, len(ids))


if __name__ == "__main__":
    unittest.main()

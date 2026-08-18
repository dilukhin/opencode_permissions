import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "stage0_permission_config_extract.py"
spec = importlib.util.spec_from_file_location("stage0_permission_config_extract", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class Stage0EffectiveLayersExtractTests(unittest.TestCase):
    def test_legacy_global_config_json_is_supported_and_sanitized(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": {"x": {"apiKey": "SECRET"}},
                        "permission": {"bash": {"git status*": "allow"}},
                    }
                ),
                encoding="utf-8",
            )
            result = mod.extract_source(path)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["permission_view"], {"permission": {"bash": {"git status*": "allow"}}})
            self.assertNotIn("SECRET", json.dumps(result))

    def test_user_global_defaults_follow_exact_runtime_order(self):
        args = type("Args", (), {"user_global_defaults": True, "managed_defaults": False, "config": []})()
        with mock.patch.object(mod.Path, "home", return_value=Path("/home/tester")):
            paths = mod.selected_paths(args)
        self.assertEqual(
            [path.name for path in paths],
            ["config.json", "opencode.json", "opencode.jsonc"],
        )

    def test_managed_defaults_use_windows_programdata_without_reading_env_values(self):
        args = type("Args", (), {"user_global_defaults": False, "managed_defaults": True, "config": []})()
        with mock.patch.object(mod.sys, "platform", "win32"), mock.patch.dict(
            os.environ,
            {"ProgramData": r"C:\ProgramData"},
            clear=False,
        ):
            paths = mod.selected_paths(args)
        self.assertEqual(paths[0], Path(r"C:\ProgramData") / "opencode" / "opencode.json")
        self.assertEqual(paths[1], Path(r"C:\ProgramData") / "opencode" / "opencode.jsonc")

    def test_permission_environment_presence_never_returns_values(self):
        secret = "DO_NOT_EXPOSE_THIS_PERMISSION_JSON"
        with mock.patch.dict(
            os.environ,
            {
                "OPENCODE_PERMISSION": secret,
                "OPENCODE_CONFIG": r"C:\secret\opencode.json",
                "OPENCODE_CONFIG_CONTENT": "SECRET_CONFIG_CONTENT",
            },
            clear=False,
        ):
            result = mod.permission_environment_presence()
        self.assertTrue(result["OPENCODE_PERMISSION"])
        self.assertTrue(result["OPENCODE_CONFIG"])
        self.assertTrue(result["OPENCODE_CONFIG_CONTENT"])
        rendered = json.dumps(result)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("SECRET_CONFIG_CONTENT", rendered)
        self.assertNotIn(r"C:\secret\opencode.json", rendered)

    def test_build_output_marks_raw_config_and_environment_values_not_retained(self):
        output = mod.build_output([])
        self.assertEqual(output["schema"], 2)
        self.assertFalse(output["raw_config_retained"])
        self.assertFalse(output["environment_values_retained"])


if __name__ == "__main__":
    unittest.main()

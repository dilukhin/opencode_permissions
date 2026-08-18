import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "stage0_permission_config_extract.py"
spec = importlib.util.spec_from_file_location("stage0_permission_config_extract", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class Stage0PermissionConfigExtractTests(unittest.TestCase):
    def test_jsonc_comments_and_trailing_commas_are_supported(self):
        text = r'''
        {
          // provider data must not survive extraction
          "provider": {"x": {"apiKey": "SECRET"}},
          "permission": {
            "bash": {
              "git status *": "allow",
            },
          },
          "default_agent": "build",
          "agent": {
            "build": {
              "mode": "primary",
              "permission": {"edit": "ask"},
              "model": "provider/model",
            },
          },
        }
        '''
        parsed = mod.parse_json_or_jsonc(text)
        view = mod.extract_permission_view(parsed)
        self.assertEqual(view["permission"]["bash"]["git status *"], "allow")
        self.assertEqual(view["default_agent"], "build")
        self.assertEqual(view["agent"]["build"]["permission"], {"edit": "ask"})
        self.assertNotIn("provider", view)
        self.assertNotIn("SECRET", json.dumps(view))

    def test_comment_markers_inside_strings_are_preserved(self):
        parsed = mod.parse_json_or_jsonc(
            r'{"permission":{"bash":{"echo https://example.test/a/*":"allow","echo //literal":"ask"}}}'
        )
        self.assertIn("echo https://example.test/a/*", parsed["permission"]["bash"])
        self.assertIn("echo //literal", parsed["permission"]["bash"])

    def test_extract_source_does_not_emit_provider_or_prompt_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opencode.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": {"x": {"apiKey": "SECRET"}},
                        "instructions": ["SECRET INSTRUCTIONS"],
                        "permission": {"bash": "ask"},
                        "agent": {
                            "review": {
                                "permission": {"edit": "deny"},
                                "prompt": "SECRET PROMPT",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = mod.extract_source(path)
            self.assertEqual(result["status"], "ok")
            rendered = json.dumps(result)
            self.assertNotIn("SECRET", rendered)
            self.assertNotIn("provider", result["permission_view"])
            self.assertNotIn("instructions", result["permission_view"])
            self.assertNotIn("prompt", rendered)

    def test_parse_failure_does_not_leak_raw_text(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opencode.jsonc"
            path.write_text('{"provider":{"apiKey":"VERY_SECRET"}, BROKEN', encoding="utf-8")
            result = mod.extract_source(path)
            self.assertEqual(result["status"], "parse_failed")
            self.assertNotIn("VERY_SECRET", json.dumps(result))
            self.assertNotIn("content", result)

    def test_secretish_permission_value_is_refused_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opencode.json"
            path.write_text(
                json.dumps({"permission": {"bash": {"curl -H Authorization:Bearer SECRET": "allow"}}}),
                encoding="utf-8",
            )
            result = mod.extract_source(path)
            self.assertEqual(result["status"], "refused")
            self.assertEqual(result["reason"], "secretish_marker_in_permission_view")
            self.assertNotIn("permission_view", result)
            self.assertNotIn("SECRET", json.dumps(result))

    def test_unrelated_filename_is_refused_before_content_read(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "auth.json"
            path.write_text('{"token":"SECRET"}', encoding="utf-8")
            result = mod.extract_source(path)
            self.assertEqual(result["status"], "refused")
            self.assertEqual(result["reason"], "unsupported_config_filename")
            self.assertNotIn("SECRET", json.dumps(result))


if __name__ == "__main__":
    unittest.main()

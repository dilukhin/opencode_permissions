"""Synthetic log formats and aggregation. No real command or path samples."""

import importlib.util
import json
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "windows_asking_audit", Path(__file__).resolve().parents[1] / "tools" / "windows_asking_audit.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WindowsAskingAuditTests(unittest.TestCase):
    def test_quoted_nested_json_and_bare_array(self):
        nested = json.dumps(json.dumps(["git status --short"]))
        lines = [
            f'timestamp=2026-10-04T08:30:52.432Z message=asking permission=bash patterns={nested}\n',
            'message=asking permission=bash patterns=["pwd"]\n',
            'message=asking permission=bash patterns=["pwd","opaque"]\n',
            'message=asking permission=bash patterns="broken"\n',
            'message=asking permission=bash patterns=["git status --short; opaque"]\n',
            'message=asking permission=edit patterns=["pwd"]\n',
        ]
        result = module.audit(lines)
        self.assertEqual(result["asking"], 6)
        self.assertEqual(result["bash"], 5)
        self.assertEqual(result["exact_candidate_total"], 2)
        self.assertEqual(result["multiple_patterns"], 1)
        self.assertEqual(result["invalid_patterns"], 1)
        self.assertEqual(result["other_single_pattern"], 1)
        self.assertEqual(result["unknown"], 3)
        self.assertTrue(result["checksum_ok"])
        self.assertEqual(result["first_bash_utc"], "2026-10-04T08:30:52.432Z")
        self.assertEqual(result["family_single"]["git.status"], 2)  # Includes opaque suffix; diagnostic only.
        self.assertEqual(result["family_multi_any"]["other"], 1)
        self.assertEqual(result["multi_size"]["2"], 1)

    def test_family_counts_never_echo_unknown_arguments(self):
        marker = "SYNTHETIC_PRIVATE_VALUE"
        lines = [
            f'message=asking permission=bash patterns={json.dumps(json.dumps(["rg " + marker]))}',
            f'message=asking permission=bash patterns={json.dumps(json.dumps(["git diff", "powershell -Command " + marker]))}',
        ]
        result = module.audit(lines)
        self.assertEqual(result["family_single"]["rg"], 1)
        self.assertEqual(result["family_multi_any"]["git.diff"], 1)
        self.assertEqual(result["family_multi_any"]["powershell.other"], 1)
        self.assertEqual(result["multi_size"]["2"], 1)
        self.assertNotIn(marker, json.dumps(result))

    def test_non_array_and_wrong_types_fail_closed(self):
        for raw in ('"not an array"', '[1]', '[]', '{"a":1}'):
            self.assertIsNone(module.parse_patterns(f"message=asking permission=bash patterns={raw}"))


if __name__ == "__main__":
    unittest.main()

"""Portable negative checks; Windows account proof belongs to the dedicated CI job."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("yc59_windows_probe", ROOT / "tests/yc59_windows/run_boundary_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WindowsFixtureGuards(unittest.TestCase):
    def test_refuses_installed_host_before_account_or_pipe_import(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "EPHEMERAL_GITHUB_HOSTED_WINDOWS_REQUIRED"):
                probe.run_probe(Path("unused-owner-core.py"))

    def test_changed_owner_dependency_rejected_before_python_import(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.py"
            marker = Path(directory) / "executed"
            source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OWNER_CORE_DIGEST_MISMATCH"):
                probe.load_core(source)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

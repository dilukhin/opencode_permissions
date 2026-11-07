"""Run the existing exact-read adversarial corpus against the extracted owner."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/yc59_windows"))
import test_read_owner as existing
from runtime.approval_owner import ledger


def load_tests(loader, tests, pattern):
    existing.CORE = ledger
    return loader.loadTestsFromTestCase(existing.ReadOwnerTests)

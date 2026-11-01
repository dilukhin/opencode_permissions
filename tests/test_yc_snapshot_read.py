"""Synthetic owner/child-process tests. No YC or cloud/network access."""
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from yc_read_capture import CaptureError, bounded_capture
from yc_read_projection import ProjectionError, SnapshotSelection
from yc_snapshot_read import ReadContext, ReadError, ReadProfile, canonical, dispatch_read

PRIVATE = "SYNTHETIC_PRIVATE_SENTINEL"
UUIDS = [f"{i:08d}-1111-4111-8111-111111111111" for i in range(1, 7)]


def context(platform=None):
    platform = platform or ("windows" if os.name == "nt" else "linux")
    return ReadContext(SnapshotSelection("synthetic-folder", "synthetic-vm", "synthetic-disk", "synthetic-snapshot"),
        "synthetic-cloud", UUIDS[0], time.monotonic(), UUIDS[1], UUIDS[2], UUIDS[3], "a" * 64,
        "C:\\fixture\\yc.exe" if platform == "windows" else "/fixture/yc",
        "fixture-file-identity", "b" * 64, "fixture-version",
        "C:\\fixture" if platform == "windows" else "/fixture", "fixture-environment", UUIDS[4], platform)


def responses():
    return [
        {"id": "synthetic-vm", "folderId": "synthetic-folder", "bootDisk": {"diskId": "synthetic-disk"},
         "metadata": {"user-data": PRIVATE}},
        {"id": "synthetic-disk", "folderId": "synthetic-folder", "instanceIds": ["synthetic-vm"],
         "size": "9007199254740993", "typeId": "network-ssd", "zoneId": "ru-central1-a", "status": "READY", "name": PRIVATE},
        {"id": "synthetic-snapshot", "folderId": "synthetic-folder", "sourceDiskId": "synthetic-disk",
         "diskSize": "9007199254740993", "status": "READY", "createdAt": "2026-11-01T10:00:00.123456789Z", "description": PRIVATE}]


def child(code):
    return subprocess.Popen([sys.executable, "-I", "-c", code], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)


class ReadProfileTests(unittest.TestCase):
    def setUp(self):
        self.ctx = context()
        self.native = "ask"
        self.profile = ReadProfile(lambda: self.ctx, lambda _: self.native)

    def test_only_three_exact_addressed_getters_are_constructed_on_both_platforms(self):
        for platform in ("windows", "linux"):
            self.ctx = context(platform)
            operation = self.profile.operation()
            steps = operation["execution"]["argv"]
            self.assertEqual([s[2] for s in steps], ["instance", "disk", "snapshot"])
            self.assertEqual([s[5] for s in steps], ["synthetic-vm", "synthetic-disk", "synthetic-snapshot"])
            self.assertTrue(all(s[3:5] == ["get", "--id"] for s in steps))
            self.assertTrue(all(s[10:14] == ["--format", "json-rest", "--retry", "0"] for s in steps))
            self.assertEqual(self.profile.canonicalize(operation), canonical(operation))

    def test_every_context_binding_changes_canonical_operation(self):
        raw = canonical(self.profile.operation())
        mutations = {"cloud_id": "other-cloud", "observation_id": UUIDS[5],
            "observed_monotonic": self.ctx.observed_monotonic - 0.001, "session_id": UUIDS[5],
            "call_id": UUIDS[5], "execution_host_id": UUIDS[5], "policy_revision": "c" * 64,
            "executable_identity": "other-file", "executable_sha256": "c" * 64, "yc_version": "other-version",
            "environment_identity": "other-env", "credential_context_id": UUIDS[5],
            "cwd": "C:\\other" if os.name == "nt" else "/other",
            "executable_path": "C:\\other\\yc.exe" if os.name == "nt" else "/other/yc"}
        original = self.ctx
        for key, value in mutations.items():
            with self.subTest(key=key):
                self.ctx = replace(original, **{key: value})
                with self.assertRaises(ReadError):
                    self.profile.check_consumption(raw)
        for key in ("folder_id", "vm_id", "disk_id", "snapshot_id"):
            self.ctx = replace(original, selection=replace(original.selection, **{key: "synthetic-other"}))
            with self.subTest(key=key), self.assertRaises(ReadError):
                self.profile.check_consumption(raw)

    def test_approval_fields_mutations_lists_and_extra_flags_cannot_be_proposed(self):
        for change in ("approved", "list", "create", "extra_flag", "format", "bool_timeout"):
            op = self.profile.operation()
            if change == "approved":
                op["approved"] = True
            elif change in ("list", "create"):
                op["execution"]["argv"][2][3] = change
            elif change == "extra_flag":
                op["execution"]["argv"][2].extend(["--profile", PRIVATE])
            elif change == "format":
                op["execution"]["argv"][2][11] = "json"
            else:
                op["execution"]["total_timeout_seconds"] = True
            with self.subTest(change=change), self.assertRaises(ReadError):
                self.profile.canonicalize(op)

    def test_stale_future_observation_and_native_veto_fail_before_pending(self):
        for offset in (-61, 2):
            self.ctx = replace(context(), observed_monotonic=time.monotonic() + offset)
            with self.assertRaisesRegex(ReadError, "YC_READ_OBSERVATION_STALE"):
                self.profile.operation()
        self.ctx = context()
        for value in ("deny", "unavailable", True, None):
            self.native = value
            with self.assertRaises(ReadError):
                self.profile.operation()

    def test_provider_exception_does_not_disclose_private_diagnostics(self):
        def broken(*_):
            raise RuntimeError(PRIVATE)
        for profile in (ReadProfile(broken, lambda _: "ask"), ReadProfile(lambda: self.ctx, broken)):
            with self.subTest(provider=profile), self.assertRaisesRegex(ReadError, "^YC_READ_PROVIDER_UNAVAILABLE$") as caught:
                profile.operation()
            self.assertIsNone(caught.exception.__context__)


class CaptureTests(unittest.TestCase):
    def test_both_streams_drained_but_only_bounded_stdout_returned(self):
        raw = bounded_capture(lambda: child(f"import sys;sys.stderr.write({PRIVATE!r});sys.stdout.buffer.write(b'{{}}')"),
                              deadline=time.monotonic() + 10)
        self.assertEqual(raw, b"{}")

    def test_limits_nonzero_and_timeout_return_fixed_codes_without_raw_output(self):
        cases = [("import sys;sys.stdout.buffer.write(b'x'*65537)", "YC_READ_OUTPUT_LIMIT", 10),
                 ("import sys;sys.stderr.buffer.write(b'x'*8193)", "YC_READ_STDERR_LIMIT", 10),
                 (f"import sys;sys.stderr.write({PRIVATE!r});sys.exit(3)", "YC_READ_EXIT_NONZERO", 10),
                 ("import time;time.sleep(10)", "YC_READ_TIMEOUT", 0.15)]
        for code, expected, timeout in cases:
            processes = []
            def start():
                processes.append(child(code))
                return processes[-1]
            with self.subTest(expected=expected), self.assertRaisesRegex(CaptureError, "^" + expected + "$") as caught:
                bounded_capture(start, deadline=time.monotonic() + timeout)
            self.assertNotIn(PRIVATE, str(caught.exception))
            self.assertIsNotNone(processes[0].poll())

    def test_expired_deadline_and_failed_starter_never_return_unbounded_error(self):
        starter = Mock()
        with self.assertRaisesRegex(CaptureError, "YC_READ_TIMEOUT"):
            bounded_capture(starter, deadline=time.monotonic() - 1)
        starter.assert_not_called()
        def broken():
            raise RuntimeError(PRIVATE)
        with self.assertRaisesRegex(CaptureError, "^YC_READ_START_FAILED$") as caught:
            bounded_capture(broken, deadline=time.monotonic() + 1)
        self.assertIsNone(caught.exception.__context__)


if __name__ == "__main__":
    unittest.main()

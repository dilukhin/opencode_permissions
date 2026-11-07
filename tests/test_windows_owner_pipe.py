"""Native bounded-transport tests: local pipes only, no accounts/cloud/approvals."""
import ctypes as C
import os
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import windows_owner_boundary as boundary
import windows_owner_pipe as pipe


class PortablePipeGuards(unittest.TestCase):
    def test_only_bounded_local_pipe_names(self):
        for value in ("", "pipe", r"\\remote\pipe\name", r"\\.\pipe\a\b", r"\\.\pipe\..", r"\\.\pipe\a" + "a" * 121):
            with self.subTest(value=value), self.assertRaises(pipe.PipeError):
                pipe._address(value)
        self.assertEqual(pipe._address(r"\\.\pipe\yc59-a"), r"\\.\pipe\yc59-a")

    def test_no_windows_api_on_other_platforms(self):
        if os.name != "nt":
            with self.assertRaisesRegex(pipe.PipeError, "WINDOWS_REQUIRED"):
                pipe.Kernel()


@unittest.skipUnless(os.name == "nt", "Windows kernel required")
class NativeBoundedPipeTests(unittest.TestCase):
    def setUp(self):
        self.owner = boundary.current()
        self.agent = "S-1-5-21-100-200-300-9999"  # no account created
        self.calls = []
        def handler(channel, principal, raw):
            self.calls.append((channel, principal, raw))
            return b"reply:" + raw
        self.prefix = "yc59-bounded-" + uuid.uuid4().hex
        self.server = pipe.Transport(self.prefix, self.agent, handler, io_timeout=0.2, handler_limit=1)
        self.address = self.server.addresses["decision"]
        self.k = self.server.k

    def tearDown(self):
        self.server.close()
        self.assertFalse(self.server.failed.is_set())

    def call(self, raw=b"hello", **updates):
        kwargs = {"expected_owner": self.owner, "expected_pid": os.getpid(), "timeout": 2, **updates}
        return pipe.call(self.address, raw, **kwargs)

    def open_idle(self, address=None):
        deadline = time.monotonic() + 2
        while True:
            handle = self.k.open(address or self.address, pipe.CLIENT_ACCESS, 0, None, 3, 0x40110000, None)
            if handle != pipe.INVALID:
                return handle
            if C.get_last_error() != 231 or time.monotonic() >= deadline:
                self.fail("raw fixture connection failed")
            threading.Event().wait(0.01)

    def test_real_kernel_server_identity_and_reply_ack(self):
        self.assertEqual(self.call(), b"reply:hello")
        self.assertEqual(self.calls, [("decision", self.owner, b"hello")])

    def test_correct_pid_with_wrong_owner_sid_or_session_sends_nothing(self):
        for expected in (boundary.Principal(self.agent, self.owner.session_id),
                         boundary.Principal(self.owner.sid, self.owner.session_id + 1)):
            with self.assertRaisesRegex(pipe.PipeError, "PIPE_SERVER_PRINCIPAL_MISMATCH"):
                self.call(expected_owner=expected)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.call(), b"reply:hello")

    def test_wrong_pid_never_sends_request(self):
        with self.assertRaisesRegex(pipe.PipeError, "PIPE_SERVER_PID_MISMATCH"):
            self.call(expected_pid=os.getpid() + 1)
        self.assertEqual(self.calls, [])

    def test_idle_client_deadline_recovers_same_server(self):
        handle = self.open_idle()
        try:
            started = time.monotonic()
            self.assertEqual(self.call(), b"reply:hello")
            self.assertLess(time.monotonic() - started, 1.5)
        finally:
            self.k.close(handle)

    def test_no_ack_cannot_hold_channel_indefinitely(self):
        handle = self.open_idle()
        try:
            self.k.transfer(handle, "write", deadline=time.monotonic() + 1,
                            stop=threading.Event(), raw=b"no-ack")
            self.assertEqual(self.call(), b"reply:hello")
            self.assertEqual(len(self.calls), 2)
        finally:
            self.k.close(handle)

    def test_oversize_request_is_disconnected_without_handler(self):
        handle = self.open_idle()
        try:
            # Hostile writer bypasses the safe client's size validation.
            original = pipe.LIMIT
            try:
                pipe.LIMIT = original + 1
                try:
                    self.k.transfer(handle, "write", deadline=time.monotonic() + 1,
                                    stop=threading.Event(), raw=b"x" * (original + 1))
                except pipe.PipeError:
                    pass  # completion vs disconnect is a legitimate Windows race
            finally:
                pipe.LIMIT = original
        finally:
            self.k.close(handle)
        self.assertEqual(self.call(), b"reply:hello")
        self.assertEqual(len(self.calls), 1)

    def test_namespace_collision_refuses_and_keeps_original(self):
        with self.assertRaisesRegex(pipe.PipeError, "PIPE_CREATE_FAILED"):
            pipe.Transport(self.prefix, self.agent, lambda *_: b"wrong", io_timeout=0.2, handler_limit=1)
        self.assertEqual(self.call(), b"reply:hello")

    def test_idle_agent_channel_does_not_block_owner_channel(self):
        # Owner can open the agent pipe but is not admitted as an agent by Transport.
        handle = self.open_idle(self.server.addresses["agent"])
        try:
            self.assertEqual(self.call(), b"reply:hello")
        finally:
            self.k.close(handle)

    def test_stop_cancels_outstanding_io_and_releases_namespace(self):
        handle = self.open_idle()
        try:
            started = time.monotonic()
            self.server.close()
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertTrue(all(not t.is_alive() for t in self.server.threads))
        finally:
            self.k.close(handle)
        with pipe.Transport(self.prefix, self.agent, lambda *_: b"new", io_timeout=0.2, handler_limit=1) as replacement:
            self.assertEqual(pipe.call(replacement.addresses["decision"], b"test", expected_owner=self.owner), b"new")


if __name__ == "__main__":
    unittest.main()

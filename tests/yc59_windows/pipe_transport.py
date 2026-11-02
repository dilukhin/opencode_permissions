"""Windows-only, synthetic named-pipe adapter to the existing test Ledger.

Not a service, executor, human-consent UI, or supported deployment interface.
Blocking I/O is bounded by the enclosing CI process timeout, not a production
per-client deadline. An unresponsive client can deny service to this fixture.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import json
import os
import threading
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import windows_owner_boundary as boundary

if os.name != "nt":
    raise RuntimeError("WINDOWS_REQUIRED")

K = C.WinDLL("kernel32", use_last_error=True)
A = C.WinDLL("advapi32", use_last_error=True)
INVALID = C.c_void_p(-1).value
LIMIT = 65536
CLIENT_ACCESS = 0x12019B  # read/write data, attributes, EA, control, synchronize; NOT create-instance


class SecurityAttributes(C.Structure):
    _fields_ = [("length", W.DWORD), ("descriptor", C.c_void_p), ("inherit", W.BOOL)]


def api(dll, name, restype, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, list(args)
    return fn


close = api(K, "CloseHandle", W.BOOL, W.HANDLE)
local_free = api(K, "LocalFree", C.c_void_p, C.c_void_p)
current_process = api(K, "GetCurrentProcess", W.HANDLE)
current_thread = api(K, "GetCurrentThread", W.HANDLE)
open_process_token = api(A, "OpenProcessToken", W.BOOL, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE))
open_thread_token = api(A, "OpenThreadToken", W.BOOL, W.HANDLE, W.DWORD, W.BOOL, C.POINTER(W.HANDLE))
token_info = api(A, "GetTokenInformation", W.BOOL, W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD))
sid_string = api(A, "ConvertSidToStringSidW", W.BOOL, C.c_void_p, C.POINTER(W.LPWSTR))
security_descriptor = api(A, "ConvertStringSecurityDescriptorToSecurityDescriptorW", W.BOOL,
                          W.LPCWSTR, W.DWORD, C.POINTER(C.c_void_p), C.POINTER(W.DWORD))
create_pipe = api(K, "CreateNamedPipeW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD,
                  W.DWORD, W.DWORD, W.DWORD, C.POINTER(SecurityAttributes))
connect = api(K, "ConnectNamedPipe", W.BOOL, W.HANDLE, C.c_void_p)
disconnect = api(K, "DisconnectNamedPipe", W.BOOL, W.HANDLE)
flush = api(K, "FlushFileBuffers", W.BOOL, W.HANDLE)
read = api(K, "ReadFile", W.BOOL, W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p)
write = api(K, "WriteFile", W.BOOL, W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p)
impersonate = api(A, "ImpersonateNamedPipeClient", W.BOOL, W.HANDLE)
revert = api(A, "RevertToSelf", W.BOOL)
create_file = api(K, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD,
                  C.c_void_p, W.DWORD, W.DWORD, W.HANDLE)
server_pid = api(K, "GetNamedPipeServerProcessId", W.BOOL, W.HANDLE, C.POINTER(W.ULONG))


def checked(ok):
    if not ok:
        raise C.WinError(C.get_last_error())


def token_sid(token):
    size = W.DWORD()
    token_info(token, 1, None, 0, C.byref(size))  # TokenUser
    if not 0 < size.value <= LIMIT:
        raise RuntimeError("TOKEN_SIZE")
    buf = C.create_string_buffer(size.value)
    checked(token_info(token, 1, buf, size, C.byref(size)))
    pointer = C.cast(buf, C.POINTER(C.c_void_p))[0]  # TOKEN_USER.Sid
    output = W.LPWSTR()
    checked(sid_string(pointer, C.byref(output)))
    try:
        return output.value
    finally:
        local_free(C.cast(output, C.c_void_p))


def current_sid():
    token = W.HANDLE()
    checked(open_process_token(current_process(), 8, C.byref(token)))
    try:
        return token_sid(token)
    finally:
        close(token)


def peer_principal(pipe):
    # Must follow successful ReadFile: Windows authenticates the LAST READ message.
    checked(impersonate(pipe))
    token = W.HANDLE()
    try:
        checked(open_thread_token(current_thread(), 8, True, C.byref(token)))
        return boundary.from_token(token)
    finally:
        if token:
            close(token)
        if not revert():
            os._exit(70)  # Never continue in a client's security context.


def peer_sid(pipe):
    return peer_principal(pipe).sid


def receive(handle):
    data, count = C.create_string_buffer(LIMIT + 1), W.DWORD()
    checked(read(handle, data, LIMIT + 1, C.byref(count), None))
    if count.value > LIMIT:
        raise ValueError("INPUT_LIMIT")
    return data.raw[:count.value]


def send(handle, value):
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(raw) > LIMIT:
        raise ValueError("OUTPUT_LIMIT")
    count = W.DWORD()
    checked(write(handle, raw, len(raw), C.byref(count), None))
    if count.value != len(raw):
        raise ValueError("SHORT_WRITE")


def call(address, request, expected_pid):
    deadline = time.monotonic() + 5
    while True:
        # Identification token suffices for SID; no delegation or client-side elevation.
        handle = create_file(address, CLIENT_ACCESS, 0, None, 3, 0x110000, None)
        if handle != INVALID:
            break
        code = C.get_last_error()
        if code != 231 or time.monotonic() >= deadline:  # ERROR_PIPE_BUSY
            raise C.WinError(code)
        time.sleep(0.02)
    try:
        actual_pid = W.ULONG()
        checked(server_pid(handle, C.byref(actual_pid)))
        if actual_pid.value != expected_pid:
            raise ValueError("WRONG_SERVER_PROCESS")
        send(handle, request)
        return json.loads(receive(handle))
    finally:
        close(handle)


class Server:
    def __init__(self, core, owner_sid, agent_sid, policy, host, prefix, *, ttl=60,
                 canonicalizer=None, consume_check=None, consume_handler=None,
                 require_separate_sessions=True):
        self.core = core
        self.owner = boundary.current()
        if self.owner.sid != owner_sid:
            raise boundary.BoundaryError("OWNER_TOKEN_MISMATCH")
        self.agent_sid, self.require_separate_sessions = agent_sid, require_separate_sessions
        self.origins = {}
        hooks = {} if canonicalizer is None else {"canonicalizer": canonicalizer}
        self.ledger = core.Ledger(owner_sid, [agent_sid], policy, host, ttl=ttl,
                                  consume_check=consume_check, **hooks)
        self.consume_handler = consume_handler  # Trusted bootstrap only, never JSON.
        self.addresses = {name: rf"\\.\pipe\{prefix}-{name}" for name in ("agent", "decision")}
        self.handles, self.threads, self.errors = [], [], []
        for channel, address in self.addresses.items():
            # Protected DACL: no inherited Everyone/Anonymous/Administrators ACE.
            # Agent may read/write data but cannot create another pipe instance.
            acl = f"D:P(A;;GA;;;SY)(A;;GA;;;{owner_sid})"
            if channel == "agent":
                acl += f"(A;;0x{CLIENT_ACCESS:x};;;{agent_sid})"
            descriptor = C.c_void_p()
            checked(security_descriptor(acl, 1, C.byref(descriptor), None))
            try:
                attrs = SecurityAttributes(C.sizeof(SecurityAttributes), descriptor, False)
                handle = create_pipe(address, 3 | 0x80000, 4 | 2 | 8, 1, LIMIT, LIMIT, 0, C.byref(attrs))
                if handle == INVALID:
                    raise C.WinError(C.get_last_error())
                self.handles.append(handle)
            finally:
                local_free(descriptor)
            thread = threading.Thread(target=self._serve, args=(handle, channel), daemon=True)
            self.threads.append(thread)
        for thread in self.threads:
            thread.start()

    def _serve(self, handle, channel):
        try:
            while True:
                if not connect(handle, None) and C.get_last_error() != 535:  # already connected
                    raise C.WinError(C.get_last_error())
                try:
                    raw = receive(handle)
                    peer = peer_principal(handle)
                    sid = peer.sid
                    if channel == "agent" and self.require_separate_sessions:
                        boundary.admit(self.owner, peer, self.agent_sid)
                    request = self.core.strict_json(raw)
                    if channel == "agent" and request.get("action") == "consume" and self.consume_handler is not None:
                        result = self.consume_handler(self.ledger, sid, request)
                    else:
                        result = self.ledger.handle(channel, sid, request)
                    if channel == "agent" and request.get("action") == "propose":
                        self.origins[result["request_id"]] = {"sid": peer.sid, "session_id": peer.session_id}
                    if channel == "decision" and request.get("action") == "inspect":
                        result = {**result, "owner_actor": {"sid": self.owner.sid, "session_id": self.owner.session_id},
                                  "request_origin": self.origins.get(result["request_id"]),
                                  "session_separation_required": self.require_separate_sessions}
                    send(handle, {"ok": True, **result})
                except self.core.Refusal as error:
                    send(handle, {"ok": False, "code": str(error)})
                except boundary.BoundaryError as error:
                    send(handle, {"ok": False, "code": str(error)})
                except (OSError, ValueError):
                    # Broken/oversized/malformed clients never produce an authorization.
                    try:
                        send(handle, {"ok": False, "code": "TRANSPORT_REFUSED"})
                    except OSError:
                        pass
                finally:
                    flush(handle)  # Do not discard a reply before the client reads it.
                    disconnect(handle)
        except Exception as error:
            self.errors.append(type(error).__name__)

    # Process-lifetime fixture. No daemon, persistence, recovery or production shutdown API.

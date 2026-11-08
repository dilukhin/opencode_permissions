"""Owner-side context and exact starter, AFTER the pinned native bootstrap.

No standalone CLI. The native parent must hold the interpreter, this component,
selection and cwd; seal process/token/default DACL before the first Python
instruction; and own the kill-on-close job. Python cannot establish that trust.
Credentials come only from the protected owner's local UI, never the protocol.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import hashlib
import os
from pathlib import PureWindowsPath
import re
import subprocess
import time
import uuid

import windows_owner_boundary as boundary
from yc_owner_native_veto import NativeVeto
from yc_read_capture import bounded_capture
from yc_read_projection import SnapshotSelection
from yc_snapshot_read import ReadContext, ReadProfile, canonical, require

YC_SHA256 = "7dc58200b8ecba6913ec3f9961d0fda21ee3b67fa6972dad0cffdde5198acb94"
YC_VERSION = "Yandex Cloud CLI 1.39.0 windows/amd64"
YC_SIZE = 196325832


def _api(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.argtypes, function.restype = list(arguments), result
    return function


class HeldObject:
    """Retain the exact kernel object already admitted by the native parent."""
    class Info(C.Structure):
        _fields_ = [("attributes", W.DWORD), ("creation", W.FILETIME), ("access", W.FILETIME),
                    ("write", W.FILETIME), ("volume", W.DWORD), ("size_high", W.DWORD),
                    ("size_low", W.DWORD), ("links", W.DWORD), ("index_high", W.DWORD), ("index_low", W.DWORD)]

    def __init__(self, path, *, directory=False, expected_sha256=None, expected_size=None):
        require(os.name == "nt", "YC_OWNER_WINDOWS_REQUIRED")
        require(type(path) is str and 0 < len(path) < 248 and "\0" not in path)
        lexical = PureWindowsPath(path)
        require(lexical.is_absolute() and not path.startswith(("\\\\", "//"))
                and ":" not in path[2:] and ".." not in lexical.parts)
        self.path, self.directory, self.handle = path, directory, None
        k = C.WinDLL("kernel32", use_last_error=True)
        self._close = _api(k, "CloseHandle", W.BOOL, W.HANDLE)
        self._info = _api(k, "GetFileInformationByHandle", W.BOOL, W.HANDLE, C.POINTER(self.Info))
        self._final = _api(k, "GetFinalPathNameByHandleW", W.DWORD, W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD)
        create = _api(k, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD,
                      C.c_void_p, W.DWORD, W.DWORD, W.HANDLE)
        handle = create(path, 0x20080 if directory else 0x80020000, 1, None, 3,
                        0x200000 | (0x2000000 if directory else 0), None)
        require(handle not in (None, C.c_void_p(-1).value), "YC_OWNER_CONTEXT_OPEN_FAILED")
        self.handle = handle
        try:
            self.identity, self.size = self._observe()
            if expected_size is not None:
                require(self.size == expected_size, "YC_OWNER_CONTEXT_SIZE_CHANGED")
            if expected_sha256 is not None:
                require(not directory and type(expected_sha256) is str
                        and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None)
                require(self.size <= 256 * 1024 * 1024, "YC_OWNER_CONTEXT_SIZE_LIMIT")
                # The retained share-read-only handle prevents replacement/write
                # while opening a second read stream for the same canonical path.
                with open(path, "rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                require(digest == expected_sha256, "YC_OWNER_CONTEXT_HASH_CHANGED")
                self.check()
        except BaseException:
            self.close()
            raise

    def _observe(self):
        require(self.handle is not None, "YC_OWNER_CONTEXT_CLOSED")
        info, final = self.Info(), C.create_unicode_buffer(1024)
        require(self._info(self.handle, C.byref(info)), "YC_OWNER_CONTEXT_INFO_UNAVAILABLE")
        require(not info.attributes & 0x400 and bool(info.attributes & 0x10) == self.directory,
                "YC_OWNER_CONTEXT_SPECIAL_OBJECT")
        require(self.directory or info.links == 1, "YC_OWNER_CONTEXT_SPECIAL_OBJECT")
        length = self._final(self.handle, final, 1024, 0)
        require(0 < length < 1024, "YC_OWNER_CONTEXT_PATH_UNAVAILABLE")
        observed = final.value.removeprefix("\\\\?\\")
        require(observed.casefold() == self.path.casefold(), "YC_OWNER_CONTEXT_PATH_CHANGED")
        identity = f"win-file:{info.volume:08x}:{info.index_high:08x}{info.index_low:08x}"
        return identity, (info.size_high << 32) | info.size_low

    def check(self):
        identity, size = self._observe()
        require(identity == self.identity and (self.directory or size == self.size), "YC_OWNER_CONTEXT_CHANGED")

    def close(self):
        if self.handle is not None:
            self._close(self.handle)
            self.handle = None


class WindowsReadContext:
    def __init__(self, *, selection, cloud_id, observed_monotonic, yc_path, cwd, native_policy_path, yc_policy_path,
                 native_sha256, yc_policy_sha256, iam_token):
        require(os.name == "nt", "YC_OWNER_WINDOWS_REQUIRED")
        self.owner = boundary.current()
        require(self.owner.session_id != 0, "YC_OWNER_INTERACTIVE_REQUIRED")
        require(type(selection) is SnapshotSelection)
        require(type(iam_token) is str and re.fullmatch(r"[\x21-\x7e]{1,4096}", iam_token) is not None,
                "YC_OWNER_CREDENTIAL_REQUIRED")
        self._held, self._closed = [], False
        try:
            self.binary = self._hold(yc_path, expected_sha256=YC_SHA256, expected_size=YC_SIZE)
            self.directory = self._hold(cwd, directory=True)
            native = self._hold(native_policy_path, expected_sha256=native_sha256)
            yc_policy = self._hold(yc_policy_path, expected_sha256=yc_policy_sha256)
            require(native.size <= 65536 and yc_policy.size <= 65536, "YC_OWNER_POLICY_SIZE_LIMIT")
            with open(native.path, "rb") as stream:
                native_bytes = stream.read(65537)
            with open(yc_policy.path, "rb") as stream:
                yc_bytes = stream.read(65537)
            self.veto = NativeVeto(native_bytes, yc_bytes, native_sha256=native_sha256, yc_sha256=yc_policy_sha256)
            system_root = os.environ["SystemRoot"]  # rebuilt by native parent from OS
            public_environment = {"SystemRoot": system_root, "PATH": str(PureWindowsPath(system_root) / "System32"),
                                  "TEMP": cwd, "TMP": cwd, "USERPROFILE": cwd,
                                  "APPDATA": cwd, "LOCALAPPDATA": cwd, "YC_CONFIG_DIR": cwd}
            # Exact IAM token overrides saved credentials. No ambient proxy,
            # endpoint, profile, shell, plugin, or Python environment is inherited.
            self._environment = {**public_environment, "YC_IAM_TOKEN": iam_token}
            version = bounded_capture(lambda: self._spawn((yc_path, "version"), public_environment),
                                      deadline=time.monotonic() + 10)
            require(version.decode("ascii").strip() == YC_VERSION, "YC_OWNER_CLI_VERSION_CHANGED")
            self._context = ReadContext(selection, cloud_id, str(uuid.uuid4()), observed_monotonic,
                str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), self.veto.revision,
                yc_path, self.binary.identity, YC_SHA256, YC_VERSION.replace(" ", "_"), cwd,
                hashlib.sha256(canonical(public_environment)).hexdigest(), str(uuid.uuid4()), "windows")
            self.profile = ReadProfile(self.current, self.veto.check)
            self.profile.operation()  # validate every selected ID/binding before hosting
        except BaseException:
            self.close()
            raise

    def _hold(self, path, **options):
        held = HeldObject(path, **options)
        self._held.append(held)
        return held

    def current(self):
        require(not self._closed and boundary.current() == self.owner, "YC_OWNER_CONTEXT_ACTOR_CHANGED")
        for held in self._held:
            held.check()
        return self._context

    def _spawn(self, argv, environment):
        require(not self._closed and boundary.current() == self.owner, "YC_OWNER_CONTEXT_ACTOR_CHANGED")
        for held in self._held:
            held.check()
        return subprocess.Popen(list(argv), executable=self.binary.path, cwd=self.directory.path,
            env=dict(environment), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def start(self, execution, argv):
        operation = self.profile.operation()
        require(type(argv) is tuple and list(argv) in operation["execution"]["argv"]
                and canonical(execution) == canonical(operation["execution"]), "YC_OWNER_SPAWN_BINDING_CHANGED")
        return self._spawn(argv, self._environment)

    def close(self):
        self._closed = True
        if hasattr(self, "_environment"):
            self._environment.clear()
        for held in reversed(self._held):
            held.close()
        self._held.clear()

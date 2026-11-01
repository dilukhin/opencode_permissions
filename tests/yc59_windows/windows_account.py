"""Temporary non-admin account/process fixture for disposable hosted CI only."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import secrets
import subprocess
import uuid

import pipe_transport as pipe

N = C.WinDLL("netapi32", use_last_error=True)


class UserInfo(C.Structure):
    _fields_ = [("name", W.LPWSTR), ("password", W.LPWSTR), ("password_age", W.DWORD),
                ("privilege", W.DWORD), ("home", W.LPWSTR), ("comment", W.LPWSTR),
                ("flags", W.DWORD), ("script", W.LPWSTR)]


class StartupInfo(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR),
                ("title", W.LPWSTR), ("x", W.DWORD), ("y", W.DWORD), ("xsize", W.DWORD),
                ("ysize", W.DWORD), ("xchars", W.DWORD), ("ychars", W.DWORD),
                ("fill", W.DWORD), ("flags", W.DWORD), ("show", W.WORD), ("reserved2size", W.WORD),
                ("reserved2", C.c_void_p), ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


user_add = pipe.api(N, "NetUserAdd", W.DWORD, W.LPCWSTR, W.DWORD, C.c_void_p, C.POINTER(W.DWORD))
user_del = pipe.api(N, "NetUserDel", W.DWORD, W.LPCWSTR, W.LPCWSTR)
logon = pipe.api(pipe.A, "LogonUserW", W.BOOL, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR,
                 W.DWORD, W.DWORD, C.POINTER(W.HANDLE))
create_process = pipe.api(pipe.A, "CreateProcessWithLogonW", W.BOOL, W.LPCWSTR, W.LPCWSTR,
                          W.LPCWSTR, W.DWORD, W.LPCWSTR, W.LPWSTR, W.DWORD, C.c_void_p,
                          W.LPCWSTR, C.POINTER(StartupInfo), C.POINTER(ProcessInfo))
wait = pipe.api(pipe.K, "WaitForSingleObject", W.DWORD, W.HANDLE, W.DWORD)
exit_code = pipe.api(pipe.K, "GetExitCodeProcess", W.BOOL, W.HANDLE, C.POINTER(W.DWORD))
terminate = pipe.api(pipe.K, "TerminateProcess", W.BOOL, W.HANDLE, W.UINT)


class TemporaryAccount:
    def __init__(self):
        self.name = "yc59_" + uuid.uuid4().hex[:12]
        self.password = "aA9!" + secrets.token_urlsafe(24)
        self.created = False

    def __enter__(self):
        # Do not allow direct imports to turn the fixture into an installed-host tool.
        if (os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
            raise RuntimeError("EPHEMERAL_HOSTED_CI_REQUIRED")
        info = UserInfo(self.name, self.password, 0, 1, None, "YC59 disposable CI fixture",
                        0x1 | 0x200 | 0x10000, None)  # USER_PRIV_USER, normal account, never admin
        parameter = W.DWORD()
        status = user_add(None, 1, C.byref(info), C.byref(parameter))
        if status:
            raise RuntimeError(f"TEMP_ACCOUNT_CREATE_FAILED:{status}")
        self.created = True
        try:
            token = W.HANDLE()
            pipe.checked(logon(self.name, ".", self.password, 2, 0, C.byref(token)))
            try:
                self.sid = pipe.token_sid(token)
            finally:
                pipe.close(token)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def run(self, argv, directory):
        # No password in argv/environment/logs; no inherited CI tokens or credentials.
        env = {"SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
               "PATH": str(Path(argv[0]).parent) + ";" + str(Path(os.environ["SystemRoot"]) / "System32"),
               "TEMP": str(directory), "TMP": str(directory), "PYTHONDONTWRITEBYTECODE": "1"}
        environment = C.create_unicode_buffer("\0".join(f"{k}={v}" for k, v in sorted(env.items())) + "\0\0")
        command = subprocess.list2cmdline(argv)
        if len(command) >= 1024:
            raise RuntimeError("FIXTURE_COMMAND_TOO_LONG")
        startup, process = StartupInfo(), ProcessInfo()
        startup.cb = C.sizeof(startup)
        pipe.checked(create_process(self.name, ".", self.password, 0, argv[0], C.create_unicode_buffer(command),
                                    0x400 | 0x08000000, environment, str(directory),
                                    C.byref(startup), C.byref(process)))
        try:
            if wait(process.process, 30000) != 0:
                terminate(process.process, 71)  # Only this fixture-created child handle.
                wait(process.process, 5000)
                raise RuntimeError("AGENT_CHILD_TIMEOUT")
            code = W.DWORD()
            pipe.checked(exit_code(process.process, C.byref(code)))
            if code.value:
                raise RuntimeError(f"AGENT_CHILD_FAILED:{code.value}")
        finally:
            pipe.close(process.thread)
            pipe.close(process.process)

    def __exit__(self, *unused):
        if self.created:
            status = user_del(None, self.name)
            self.created = False
            self.password = None
            if status:
                raise RuntimeError(f"TEMP_ACCOUNT_DELETE_FAILED:{status}")

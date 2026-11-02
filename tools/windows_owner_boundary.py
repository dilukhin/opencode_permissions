"""Windows actor observations and conservative interactive-owner admission.

Principal validation alone is not provenance. Live endpoints must obtain these
facts from process/client tokens, never an agent-supplied JSON report.
"""
from dataclasses import dataclass
import os
import re


class BoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    sid: str
    session_id: int


def validate(value):
    if (type(value) is not Principal or type(value.sid) is not str
            or re.fullmatch(r"S-1-[0-9]+(?:-[0-9]+)+", value.sid) is None
            or type(value.session_id) is not int or not 0 <= value.session_id <= 0xFFFFFFFF):
        raise BoundaryError("WINDOWS_PRINCIPAL_INVALID")


def admit(owner, agent, expected_agent_sid):
    validate(owner)
    validate(agent)
    if owner.sid == agent.sid:
        raise BoundaryError("OWNER_AGENT_SID_SAME")
    if agent.sid != expected_agent_sid:
        raise BoundaryError("WRONG_AGENT_SID")
    if owner.session_id == 0 or agent.session_id == 0:
        raise BoundaryError("INTERACTIVE_WINDOWS_SESSIONS_REQUIRED")
    if owner.session_id == agent.session_id:
        raise BoundaryError("SEPARATE_WINDOWS_SESSIONS_REQUIRED")


def from_token(token):
    if os.name != "nt":
        raise BoundaryError("WINDOWS_REQUIRED")
    import ctypes as C
    from ctypes import wintypes as W
    api = C.WinDLL("advapi32", use_last_error=True)
    kernel = C.WinDLL("kernel32", use_last_error=True)
    info = api.GetTokenInformation
    info.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
    info.restype = W.BOOL
    convert = api.ConvertSidToStringSidW
    convert.argtypes = [C.c_void_p, C.POINTER(W.LPWSTR)]
    convert.restype = W.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [C.c_void_p], C.c_void_p
    size = W.DWORD()
    info(token, 1, None, 0, C.byref(size))
    if not 0 < size.value <= 65536:
        raise BoundaryError("WINDOWS_TOKEN_SIZE_INVALID")
    buf = C.create_string_buffer(size.value)
    if not info(token, 1, buf, size, C.byref(size)):
        raise BoundaryError("WINDOWS_TOKEN_QUERY_FAILED")
    sid = W.LPWSTR()
    if not convert(C.cast(buf, C.POINTER(C.c_void_p))[0], C.byref(sid)):
        raise BoundaryError("WINDOWS_SID_QUERY_FAILED")
    try:
        sid_value = sid.value
    finally:
        kernel.LocalFree(C.cast(sid, C.c_void_p))
    session = W.DWORD()
    if not info(token, 12, C.byref(session), C.sizeof(session), C.byref(size)):  # TokenSessionId
        raise BoundaryError("WINDOWS_SESSION_QUERY_FAILED")
    result = Principal(sid_value, session.value)
    validate(result)
    return result


def current():
    if os.name != "nt":
        raise BoundaryError("WINDOWS_REQUIRED")
    import ctypes as C
    from ctypes import wintypes as W
    kernel = C.WinDLL("kernel32", use_last_error=True)
    api = C.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes, kernel.GetCurrentProcess.restype = [], W.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [W.HANDLE], W.BOOL
    api.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)]
    api.OpenProcessToken.restype = W.BOOL
    token = W.HANDLE()
    if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, C.byref(token)):
        raise BoundaryError("WINDOWS_TOKEN_QUERY_FAILED")
    try:
        return from_token(token)
    finally:
        kernel.CloseHandle(token)

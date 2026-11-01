"""Owner-side exact read profile. Not an approval issuer or public CLI.

The trusted composition root supplies current facts, native veto, the existing
Ledger, and the setup-owned process starter. No caller approval fields or
caller-provided executors are accepted by the pipe protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
import time
import uuid

from yc_read_capture import CaptureError, bounded_capture
from yc_read_projection import SnapshotSelection, project_snapshot_context

PROFILE = "yc-snapshot-read/v1"
REPRESENTATION = "compute-rest-json/v1"
MAX_AGE = 60
TOTAL_TIMEOUT = 30


class ReadError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(ok, code="YC_READ_CONTEXT_INVALID"):
    if not ok:
        raise ReadError(code)


def canonical(value):
    failed = False
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        failed = True
    if failed:
        raise ReadError("YC_READ_OPERATION_INVALID")
    require(len(raw) <= 16384, "YC_READ_OPERATION_LIMIT")
    return raw


@dataclass(frozen=True, repr=False)
class ReadContext:
    selection: SnapshotSelection
    cloud_id: str
    observation_id: str
    observed_monotonic: float
    session_id: str
    call_id: str
    execution_host_id: str
    policy_revision: str
    executable_path: str
    executable_identity: str
    executable_sha256: str
    yc_version: str
    cwd: str
    environment_identity: str
    credential_context_id: str
    platform: str


class ReadProfile:
    def __init__(self, current_context, native_check, *, clock=time.monotonic):
        require(callable(current_context) and callable(native_check) and callable(clock))
        self.current_context, self.native_check, self.clock = current_context, native_check, clock

    def operation(self):
        """An unapproved proposal, rebuilt exclusively from owner-supplied facts."""
        ctx = self.current_context()
        require(type(ctx) is ReadContext and type(ctx.selection) is SnapshotSelection)
        s = ctx.selection
        for value in (ctx.cloud_id, s.folder_id, s.vm_id, s.disk_id, s.snapshot_id):
            require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,50}", value) is not None)
        for value in (ctx.observation_id, ctx.session_id, ctx.call_id, ctx.execution_host_id, ctx.credential_context_id):
            require(type(value) is str)
            try:
                valid = str(uuid.UUID(value)) == value
            except (ValueError, AttributeError):
                valid = False
            require(valid)
        for value in (ctx.policy_revision, ctx.executable_sha256):
            require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
        require(ctx.platform in {"linux", "windows"})
        path_type = PureWindowsPath if ctx.platform == "windows" else PurePosixPath
        for value in (ctx.executable_path, ctx.cwd):
            require(type(value) is str and 0 < len(value) <= 1024 and "\0" not in value)
            path = path_type(value)
            require(path.is_absolute() and ".." not in path.parts)
            if ctx.platform == "windows":
                require(not value.startswith(("\\\\", "//")) and ":" not in value[2:])
        require(ctx.platform != "windows" or PureWindowsPath(ctx.executable_path).suffix.lower() == ".exe")
        for value in (ctx.executable_identity, ctx.environment_identity, ctx.yc_version):
            require(type(value) is str and re.fullmatch(r"[\x21-\x7e]{1,256}", value) is not None)
        require(type(ctx.observed_monotonic) is float)
        require(0 <= self.clock() - ctx.observed_monotonic <= MAX_AGE, "YC_READ_OBSERVATION_STALE")
        native = self.native_check(ctx)
        require(type(native) is str and native in {"allow", "ask", "deny"}, "YC_READ_NATIVE_UNAVAILABLE")
        require(native != "deny", "YC_READ_NATIVE_DENY")
        common = ["--cloud-id", ctx.cloud_id, "--folder-id", s.folder_id,
                  "--format", "json-rest", "--retry", "0", "--no-user-output", "--no-browser"]
        steps = [[ctx.executable_path, "compute", kind, "get", "--id", target, *common]
                 for kind, target in (("instance", s.vm_id), ("disk", s.disk_id), ("snapshot", s.snapshot_id))]
        return {"schema": PROFILE, "action": "yc.snapshot.read", "session_id": ctx.session_id,
            "call_id": ctx.call_id, "execution_host_id": ctx.execution_host_id, "policy_revision": ctx.policy_revision,
            "scope": {"cloud_id": ctx.cloud_id, "folder_id": s.folder_id, "vm_id": s.vm_id,
                      "disk_id": s.disk_id, "snapshot_id": s.snapshot_id, "observation_id": ctx.observation_id,
                      "observation_monotonic_hex": ctx.observed_monotonic.hex()},
            "execution": {"platform": ctx.platform, "executable_identity": ctx.executable_identity,
                          "executable_sha256": ctx.executable_sha256, "yc_version": ctx.yc_version,
                          "cwd": ctx.cwd, "environment_identity": ctx.environment_identity,
                          "credential_context_id": ctx.credential_context_id, "stdin": "devnull",
                          "shell": False, "argv": steps, "total_timeout_seconds": TOTAL_TIMEOUT,
                          "stdout_limit_per_step": 65536, "stderr_limit_per_step": 8192},
            "projection_profile": REPRESENTATION}

    def canonicalize(self, operation):
        require(type(operation) is dict, "YC_READ_OPERATION_INVALID")
        expected = canonical(self.operation())
        require(canonical(operation) == expected, "YC_READ_OPERATION_CHANGED")
        return expected

    def check_consumption(self, raw):
        require(type(raw) is bytes and raw == canonical(self.operation()), "YC_READ_CONTEXT_CHANGED")


def dispatch_read(ledger, caller, request, *, profile, start):
    """Trusted owner bridge: consume once, capture three reads, project atomically.

start(execution, argv) must return an owned Popen with DEVNULL stdin, binary
PIPE stdout/stderr, shell=False and the exact trusted path/cwd/environment.
It must revalidate executable/config identity at its actual spawn boundary.
This callback is setup-owned, never a field of an agent request.
"""
    require(type(request) is dict and request.get("action") == "consume", "YC_READ_CONSUME_REQUIRED")
    # Existing Ledger owns identity/expiry/once. No second grant table is created.
    view = ledger.handle("agent", caller, request)
    raw = ledger.entries[view["request_id"]]["operation"]  # immutable bytes, owner-internal only
    profile.check_consumption(raw)
    operation = json.loads(raw)
    require(operation["schema"] == PROFILE)
    deadline = profile.clock() + TOTAL_TIMEOUT
    outputs = []
    for argv in operation["execution"]["argv"]:
        profile.check_consumption(raw)
        require(profile.clock() < deadline, "YC_READ_TIMEOUT")
        try:
            output = bounded_capture(lambda: start(operation["execution"], tuple(argv)),
                                     deadline=deadline, clock=profile.clock)
        except CaptureError as error:
            raise ReadError(error.code) from None
        outputs.append(output)
    profile.check_consumption(raw)
    scope = operation["scope"]
    selection = SnapshotSelection(*(scope[k] for k in ("folder_id", "vm_id", "disk_id", "snapshot_id")))
    projected = project_snapshot_context(*outputs, selection=selection)
    # Authorization and cloud provenance are NOT inferred from a successful projection.
    return {**view, "projection": projected, "profile": PROFILE,
            "logical_reads_completed": 3, "restore_verified": False}

"""Local agent-safe PreparedProcess projection; validation is NOT acquisition trust.

Only call from the trusted composition root after agent-safe prepare/revalidation.
No wire deserializer, executor, secret detector or automatic script ALLOW is added.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
from pathlib import PurePosixPath, PureWindowsPath
import re
import stat

from classifier_core import make_result, combine_native_classifier, deny_result
from normalized_operation_identity import extract_identity_core, jcs_dumps, operation_identity, strict_loads

PROFILE = "agent-safe-local-prepared/v1"
STAT_PROFILE = "agent-safe-stat/v1"
TRANSPORT = "local-inprocess/v1"
PROCESS_FIELDS = frozenset(("source_txn_id", "attempt_txn_id", "role", "manifest_sha256",
    "program", "argv", "cwd", "timeout_seconds", "stdin_utf8", "program_identity",
    "cwd_identity", "artifacts"))
ARTIFACT_FIELDS = frozenset(("artifact_id", "path", "size_bytes", "sha256", "object_identity"))
FILE_FIELDS = ("dev", "ino", "mode", "size", "mtime_ns", "ctime_ns", "file_attributes", "reparse_tag")
DIRECTORY_FIELDS = ("dev", "ino", "mode", "file_attributes", "reparse_tag")
HEX = re.compile(r"[0-9a-f]{64}\Z")
TXN = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}\Z")


class PreparedContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(ok: bool, code: str) -> None:
    if not ok:
        raise PreparedContractError(code)


def text(value: object, *, empty: bool = False, limit: int = 32768) -> str:
    require(type(value) is str, "TEXT_REQUIRED")
    require((empty or bool(value.strip())) and "\0" not in value, "INVALID_TEXT")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise PreparedContractError("INVALID_UNICODE") from None
    require(size <= limit, "TEXT_LIMIT")
    return value


def _digest(value: object) -> str:
    require(type(value) is str and HEX.fullmatch(value) is not None, "INVALID_DIGEST")
    return value


def _record(value: object, expected: frozenset[str]) -> None:
    require(not isinstance(value, type) and is_dataclass(value), "PREPARED_DATACLASS_REQUIRED")
    require(value.__dataclass_params__.frozen, "MUTABLE_PREPARED_RECORD")
    require(frozenset(f.name for f in fields(value)) == expected, "PREPARED_FIELDS_MISMATCH")


def _path(value: object, platform: str) -> str:
    value = text(value)
    path = PureWindowsPath(value) if platform == "windows" else PurePosixPath(value)
    require(path.is_absolute() and ".." not in path.parts, "ABSOLUTE_PATH_REQUIRED")
    if platform == "windows":
        require(not value.startswith(("\\\\", "//")) and ":" not in value[2:], "WINDOWS_PATH_UNSUPPORTED")
    return value


def encode_object_identity(values: tuple[int, ...], *, kind: str, platform: str) -> str:
    """Exact named decimal strings, including signed timestamps; no repr/rounding."""
    require(platform in {"linux", "windows"}, "PLATFORM_UNSUPPORTED")
    require(kind in {"file", "directory"}, "STAT_KIND_UNSUPPORTED")
    names = FILE_FIELDS if kind == "file" else DIRECTORY_FIELDS
    require(type(values) is tuple and len(values) == len(names), "STAT_SHAPE")
    require(all(type(v) is int and v.bit_length() <= 256 for v in values), "STAT_INTEGER")
    require(all(v >= 0 or name in {"mtime_ns", "ctime_ns"} for name, v in zip(names, values)), "STAT_NEGATIVE")
    require(stat.S_ISREG(values[2]) if kind == "file" else stat.S_ISDIR(values[2]), "STAT_TYPE")
    require(not values[-2] & 0x400 and values[-1] == 0, "STAT_REPARSE_UNSUPPORTED")
    return STAT_PROFILE + ":" + jcs_dumps({"platform": platform, "kind": kind,
        "components": {name: str(v) for name, v in zip(names, values)}})


@dataclass(frozen=True, repr=False)
class Projection:
    operation_json: str
    operation_identity: str
    snapshot_identity: str
    source_txn_id: str
    attempt_txn_id: str
    role: str

    def operation(self) -> dict:
        return strict_loads(self.operation_json)


def project_prepared(prepared: object, *, platform: str, profile: str = PROFILE) -> Projection:
    """Project facts from agent-safe#33; no caller-declared effects or authority."""
    require(profile == PROFILE, "PROFILE_UNSUPPORTED")
    require(platform in {"linux", "windows"}, "PLATFORM_UNSUPPORTED")
    _record(prepared, PROCESS_FIELDS)
    for value in (prepared.source_txn_id, prepared.attempt_txn_id):
        require(type(value) is str and TXN.fullmatch(value) is not None, "TRANSACTION_ID")
    require(prepared.source_txn_id != prepared.attempt_txn_id, "ATTEMPT_IS_SOURCE")
    require(type(prepared.role) is str and prepared.role in {"process", "verify"}, "ROLE_UNSUPPORTED")
    manifest = _digest(prepared.manifest_sha256)
    program, cwd = _path(prepared.program, platform), _path(prepared.cwd, platform)
    if platform == "windows":
        require(PureWindowsPath(program).suffix.lower() == ".exe", "WINDOWS_EXECUTABLE_UNSUPPORTED")
    require(type(prepared.argv) is tuple and 2 <= len(prepared.argv) <= 1024, "ARGV_SHAPE")
    argv = [text(v, empty=True) for v in prepared.argv]
    require(argv[0] == "-I", "INTERPRETER_PROFILE_UNSUPPORTED")
    require(type(prepared.timeout_seconds) is int and 1 <= prepared.timeout_seconds <= 3600, "TIMEOUT_INVALID")
    stdin = {"mode": "devnull"}
    if prepared.stdin_utf8 is not None:
        raw = text(prepared.stdin_utf8, empty=True, limit=65536).encode("utf-8")
        stdin = {"mode": "pipe", "encoding": "utf-8", "size_bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()}
    require(sum(len(v.encode("utf-8")) for v in [program, cwd, *argv]) <= 1024 * 1024, "REQUEST_LIMIT")
    executable_id = encode_object_identity(prepared.program_identity, kind="file", platform=platform)
    cwd_id = {"requested": cwd, "lexical": cwd, "follow_mode": "target",
              "object_identity": encode_object_identity(prepared.cwd_identity, kind="directory", platform=platform)}
    require(type(prepared.artifacts) is tuple and 1 <= len(prepared.artifacts) <= 32, "ARTIFACT_COUNT")
    dependencies, ids, paths = [], set(), set()
    total = 0
    for artifact in prepared.artifacts:
        _record(artifact, ARTIFACT_FIELDS)
        name = text(artifact.artifact_id, limit=64)
        require(re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) is not None and name not in ids, "ARTIFACT_ID")
        path = _path(artifact.path, platform)
        require(path not in paths, "ARTIFACT_PATH_DUPLICATE")
        require(type(artifact.size_bytes) is int and 0 <= artifact.size_bytes <= 8 * 1024 * 1024, "ARTIFACT_SIZE")
        object_id = encode_object_identity(artifact.object_identity, kind="file", platform=platform)
        require(artifact.object_identity[3] == artifact.size_bytes, "ARTIFACT_SIZE_MISMATCH")
        ids.add(name)
        paths.add(path)
        total += artifact.size_bytes
        dependencies.append({"kind": "saved_artifact", "artifact_id": name, "path": path,
            "size_bytes": artifact.size_bytes, "sha256": _digest(artifact.sha256), "object_identity": object_id})
    require(total <= 32 * 1024 * 1024, "ARTIFACT_TOTAL_LIMIT")
    require(argv[1] in paths, "SAVED_SCRIPT_REQUIRED")
    operation = {"schema": "normalized-operation/v1", "canonicalization": "op-jcs-v1",
        "platform": platform, "channel": "local", "operation_kind": "process_exec",
        "execution": {"kind": "argv", "profile": PROFILE, "shell": False,
            "executable": {"invoked": program, "resolved_path": program, "object_identity": executable_id},
            "argv": [program, *argv], "cwd": cwd_id, "stdin": stdin,
            "timeout_seconds": prepared.timeout_seconds, "environment": "inherited-unproven"},
        "targets": [{"role": "effects", "kind": "unknown_target", "identity": {"scope": "script-effects-unproven"}}],
        "effects": ["process", "unknown_code_execution"], "context_dependencies": dependencies}
    # Canonical identity normalizes dependency sets, while keeping ordered argv.
    operation = extract_identity_core(operation)
    op_id = operation_identity(operation)
    binding = {"profile": PROFILE, "operation_identity": op_id, "manifest_sha256": manifest,
        "source_txn_id": prepared.source_txn_id, "attempt_txn_id": prepared.attempt_txn_id, "role": prepared.role}
    snapshot_id = "sha256:" + hashlib.sha256(b"opencode_permissions.prepared-snapshot.v1\n" + jcs_dumps(binding).encode("utf-8")).hexdigest()
    return Projection(jcs_dumps(operation), op_id, snapshot_id,
                      prepared.source_txn_id, prepared.attempt_txn_id, prepared.role)


def classify_prepared(projection: Projection, *, native_decision: str = "ask") -> dict:
    """Reuse classifier result validation. Native allow is narrowed for opaque code."""
    require(native_decision in {"allow", "ask", "deny"}, "NATIVE_DECISION_INVALID")
    if native_decision == "deny":
        terminal = combine_native_classifier("deny")
        assert terminal["decision"] == "DENY"
        return deny_result(reason_codes=["native.hard_deny"])
    operation = projection.operation()
    return make_result("ASK_USER", reason_codes=["prepared.script_effects_unproven"],
        effects=operation["effects"], targets=operation["targets"],
        uncertainties=["prepared.script_effects_unproven", "prepared.environment_unproven"],
        normalized_operation=operation, classifier_profile_id=PROFILE)

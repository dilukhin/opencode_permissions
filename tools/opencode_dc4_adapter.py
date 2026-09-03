#!/usr/bin/env python3
"""Strict OpenCode 1.18.26 ShellTool adapter for DC-4 proof.

This is intentionally a tiny static-shell subset, not a general shell parser.
Anything outside the proven grammar fails closed to ASK_USER.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
from typing import Any

from classifier_analyzers import analyze_simple
from classifier_core import allow_result, ask_result

PROFILE_ID = "dc4-opencode-1.18.26-dash-static-v1"
FACT_SCHEMA = "parsed-simple/v1"
SUPPORTED_PLATFORM = "linux"
SUPPORTED_SHELLS = {"/bin/dash"}
SUPPORTED_EXECUTABLES = {"/usr/bin/printf": "printf"}
TOKEN_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,-]+$")
FORBIDDEN_CHARS = set("\t\r\n;&|<>`$\\'\"*?[]{}()!~")


def _ask(code: str, *, effects: list[str] | None = None) -> dict[str, Any]:
    return ask_result(
        reason_codes=[code],
        effects=effects or ["process", "unknown"],
        targets=[],
        uncertainties=[code],
    )


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_identity(path: str, st: os.stat_result) -> str:
    return (
        f"linux:dev={st.st_dev}:ino={st.st_ino}:uid={st.st_uid}:"
        f"mode={stat.S_IMODE(st.st_mode):04o}:sha256={_sha256_file(path)}"
    )


def _trusted_executable(path: str) -> tuple[dict[str, Any] | None, str | None]:
    semantic = SUPPORTED_EXECUTABLES.get(path)
    if semantic is None:
        return None, "executable.not_allowlisted"
    try:
        resolved = os.path.realpath(path)
        st = os.stat(path, follow_symlinks=True)
    except OSError:
        return None, "identity.executable_unavailable"
    if not stat.S_ISREG(st.st_mode) or not os.access(path, os.X_OK):
        return None, "identity.executable_not_regular_executable"
    if st.st_uid != 0:
        return None, "identity.executable_owner_untrusted"
    if stat.S_IMODE(st.st_mode) & 0o022:
        return None, "identity.executable_writable_by_untrusted"
    if resolved != path:
        return None, "identity.executable_symlink_unsupported"
    return {
        "invoked": path,
        "resolved_path": resolved,
        "object_identity": _object_identity(resolved, st),
        "semantic_name": semantic,
        "trust_domain": "system",
    }, None


def _path_identity(path: str, workspace_root: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        lexical = os.path.abspath(path)
        root = os.path.abspath(workspace_root)
        st = os.stat(lexical, follow_symlinks=True)
    except OSError:
        return None, "identity.cwd_unavailable"
    if not stat.S_ISDIR(st.st_mode):
        return None, "identity.cwd_not_directory"
    try:
        within = os.path.commonpath([lexical, root]) == root
    except ValueError:
        within = False
    if not within:
        return None, "target.cwd_outside_workspace"
    return {
        "requested": path,
        "lexical": lexical,
        "object_identity": (
            f"linux:dev={st.st_dev}:ino={st.st_ino}:uid={st.st_uid}:"
            f"mode={stat.S_IMODE(st.st_mode):04o}"
        ),
        "follow_mode": "target",
        "boundary": "workspace",
    }, None


def _shell_identity(shell: str) -> tuple[dict[str, Any] | None, str | None]:
    if shell not in SUPPORTED_SHELLS:
        return None, "shell.profile_unsupported"
    try:
        resolved = os.path.realpath(shell)
        st = os.stat(shell, follow_symlinks=True)
    except OSError:
        return None, "identity.shell_unavailable"
    if not stat.S_ISREG(st.st_mode) or not os.access(shell, os.X_OK):
        return None, "identity.shell_not_regular_executable"
    if st.st_uid != 0 or stat.S_IMODE(st.st_mode) & 0o022:
        return None, "identity.shell_untrusted"
    return {
        "requested": shell,
        "resolved_path": resolved,
        "object_identity": _object_identity(resolved, st),
    }, None


def _parse_static_simple(command: str) -> tuple[list[str] | None, str | None]:
    if not isinstance(command, str) or not command:
        return None, "syntax.empty"
    if command != command.strip() or "  " in command:
        return None, "syntax.whitespace_unsupported"
    if any(ch in FORBIDDEN_CHARS for ch in command):
        return None, "syntax.dynamic_or_operator"
    argv = command.split(" ")
    if not argv or any(not token or TOKEN_RE.fullmatch(token) is None for token in argv):
        return None, "syntax.token_unsupported"
    if not os.path.isabs(argv[0]):
        return None, "executable.absolute_path_required"
    return argv, None


def prepare(command: str, cwd: str, workspace_root: str, shell: str = "/bin/dash") -> dict[str, Any]:
    if sys.platform != SUPPORTED_PLATFORM:
        return {"result": _ask("platform.unsupported"), "guard": None}

    argv, error = _parse_static_simple(command)
    if error:
        return {"result": _ask(error), "guard": None}
    assert argv is not None

    shell_id, error = _shell_identity(shell)
    if error:
        return {"result": _ask(error), "guard": None}
    executable, error = _trusted_executable(argv[0])
    if error:
        return {"result": _ask(error), "guard": None}
    cwd_id, error = _path_identity(cwd, workspace_root)
    if error:
        return {"result": _ask(error), "guard": None}
    assert shell_id and executable and cwd_id

    semantic = executable["semantic_name"]
    semantic_fact = {
        "schema": FACT_SCHEMA,
        "platform": SUPPORTED_PLATFORM,
        "parser": {"status": "exact", "profile": PROFILE_ID},
        "executable": {
            "invoked": semantic,
            "resolved_path": executable["resolved_path"],
            "object_identity": executable["object_identity"],
        },
        "argv": [semantic, *argv[1:]],
        "cwd": copy.deepcopy(cwd_id),
        "targets": [],
        "redirects": [],
        "stdin": {"kind": "none"},
    }
    result = analyze_simple(semantic_fact)
    if result["decision"] != "ALLOW":
        return {"result": result, "guard": None}

    # Rebind the proven semantic result to the exact command the shell executes.
    exact_operation = copy.deepcopy(result["normalized_operation"])
    exact_operation["execution"]["executable"] = {
        "invoked": executable["invoked"],
        "resolved_path": executable["resolved_path"],
        "object_identity": executable["object_identity"],
    }
    exact_operation["execution"]["argv"] = argv
    exact_result = allow_result(
        exact_operation,
        reason_codes=[*result["reason_codes"], "adapter.exact_executable_binding"],
        classifier_profile_id=PROFILE_ID,
    )
    guard = {
        "schema": "dc4-runtime-guard/v1",
        "profile": PROFILE_ID,
        "command": command,
        "shell": shell_id,
        "executable": executable,
        "cwd": cwd_id,
        "operation_identity": exact_result["operation_identity"],
    }
    return {"result": exact_result, "guard": guard}


def revalidate(
    guard: dict[str, Any],
    command: str,
    cwd: str,
    workspace_root: str,
    shell: str = "/bin/dash",
) -> dict[str, Any]:
    if not isinstance(guard, dict) or guard.get("schema") != "dc4-runtime-guard/v1":
        return {"ok": False, "reason": "guard.invalid"}
    if guard.get("profile") != PROFILE_ID or guard.get("command") != command:
        return {"ok": False, "reason": "guard.command_mismatch"}
    fresh = prepare(command, cwd, workspace_root, shell)
    result = fresh.get("result") or {}
    fresh_guard = fresh.get("guard")
    if result.get("decision") != "ALLOW" or not isinstance(fresh_guard, dict):
        return {"ok": False, "reason": "guard.revalidation_not_allow"}
    for key in ("shell", "executable", "cwd", "operation_identity"):
        if fresh_guard.get(key) != guard.get(key):
            return {"ok": False, "reason": f"guard.{key}_changed"}
    return {"ok": True, "operation_identity": guard["operation_identity"]}


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--command", required=True)
    prep.add_argument("--cwd", required=True)
    prep.add_argument("--workspace-root", required=True)
    prep.add_argument("--shell", default="/bin/dash")
    rev = sub.add_parser("revalidate")
    rev.add_argument("--guard-file", required=True)
    rev.add_argument("--command", required=True)
    rev.add_argument("--cwd", required=True)
    rev.add_argument("--workspace-root", required=True)
    rev.add_argument("--shell", default="/bin/dash")
    args = parser.parse_args()
    if args.action == "prepare":
        payload = prepare(args.command, args.cwd, args.workspace_root, args.shell)
    else:
        payload = revalidate(
            _read_json(args.guard_file),
            args.command,
            args.cwd,
            args.workspace_root,
            args.shell,
        )
    json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

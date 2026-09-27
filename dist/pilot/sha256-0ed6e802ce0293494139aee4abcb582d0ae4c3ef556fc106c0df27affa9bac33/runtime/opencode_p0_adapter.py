#!/usr/bin/env python3
"""Production P0 adapter for the minimal managed OpenCode pilot.

The adapter intentionally supports exactly one classifier ALLOW family:
single-file grep over one existing non-secret workspace file.

It is not a general shell parser. Unsupported or opaque input fails closed to
ASK_USER. State-changing operations are outside P0.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import posixpath
import re
import stat
import sys
from pathlib import Path
from typing import Any

from classifier_analyzers import analyze_simple
from classifier_core import allow_result, ask_result

FACT_SCHEMA = "parsed-simple/v1"
SUPPORTED_PLATFORM = "linux"
GUARD_SCHEMA = "opencode-p0-runtime-guard/v1"

TOKEN_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,^:-]+$")
FORBIDDEN_CHARS = set("\t\r\n;&|<>`$\\'\"*?[]{}()!~")


def _ask(code: str, *, effects: list[str] | None = None, targets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return ask_result(
        reason_codes=[code],
        effects=effects or ["process", "unknown"],
        targets=targets or [],
        uncertainties=[code],
    )


def _load_profile(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as stream:
        profile = json.load(stream)
    if profile.get("profile_format") != "opencode-permissions-p0-classifier-profile/v1":
        raise ValueError("profile.unsupported")
    if profile.get("platform") != SUPPORTED_PLATFORM:
        raise ValueError("profile.platform_unsupported")
    target = profile.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("opencode_version"), str):
        raise ValueError("profile.target_missing")
    return profile


def _object_identity(path: str, st: os.stat_result) -> str:
    return (
        f"linux:dev={st.st_dev}:ino={st.st_ino}:uid={st.st_uid}:"
        f"mode={stat.S_IMODE(st.st_mode):04o}:size={st.st_size}:mtime_ns={st.st_mtime_ns}"
    )


def _trusted_system_executable(path: str, *, semantic_name: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
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
    result = {
        "invoked": path,
        "resolved_path": resolved,
        "object_identity": _object_identity(resolved, st),
        "trust_domain": "system",
    }
    if semantic_name is not None:
        result["semantic_name"] = semantic_name
    return result, None


def _directory_identity(path: str, workspace_root: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        lexical = os.path.abspath(path)
        root = os.path.abspath(workspace_root)
        resolved = os.path.realpath(lexical)
        resolved_root = os.path.realpath(root)
        st = os.stat(lexical, follow_symlinks=True)
    except OSError:
        return None, "identity.cwd_unavailable"
    if not stat.S_ISDIR(st.st_mode):
        return None, "identity.cwd_not_directory"
    if resolved_root != root:
        return None, "identity.workspace_symlink_unsupported"
    if resolved != lexical:
        return None, "identity.cwd_symlink_unsupported"
    try:
        within = os.path.commonpath([resolved, resolved_root]) == resolved_root
    except ValueError:
        within = False
    if not within:
        return None, "target.cwd_outside_workspace"
    return {
        "requested": path,
        "lexical": lexical,
        "resolved_path": resolved,
        "object_identity": _object_identity(resolved, st),
        "follow_mode": "target",
        "boundary": "workspace",
    }, None


def _wildcard_match(value: str, pattern: str) -> bool:
    """Match the OpenCode v1 wildcard subset used by canonical secret path rules."""
    normalized = value.replace("\\", "/")
    expression = []
    for char in pattern.replace("\\", "/"):
        if char == "*":
            expression.append(".*")
        elif char == "?":
            expression.append(".")
        else:
            expression.append(re.escape(char))
    return re.fullmatch("".join(expression), normalized, flags=re.S) is not None


def _secret_rule_match(relative_path: str, profile: dict[str, Any]) -> tuple[bool, str | None]:
    boundary = profile.get("secret_boundary") or {}
    rules = boundary.get("resolved_rules")
    if not isinstance(rules, list):
        return True, "profile.secret_boundary_missing"
    for rule in rules:
        if not isinstance(rule, dict):
            return True, "profile.secret_boundary_invalid"
        pattern = rule.get("pattern")
        rule_id = rule.get("id")
        if isinstance(pattern, str) and _wildcard_match(relative_path, pattern):
            return True, rule_id if isinstance(rule_id, str) else "secret.pattern"
    return False, None


def _file_target(requested: str, cwd: str, workspace_root: str, profile: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        root = os.path.abspath(workspace_root)
        root_real = os.path.realpath(root)
        if root_real != root:
            return None, "identity.workspace_symlink_unsupported"
        lexical = requested if posixpath.isabs(requested) else os.path.join(cwd, requested)
        lexical = os.path.abspath(lexical)
        resolved = os.path.realpath(lexical)
        if resolved != lexical:
            return None, "identity.target_symlink_unsupported"
        try:
            within = os.path.commonpath([resolved, root_real]) == root_real
        except ValueError:
            within = False
        if not within:
            return None, "target.file_outside_workspace"
        st = os.stat(lexical, follow_symlinks=True)
    except OSError:
        return None, "target.file_unavailable"
    if not stat.S_ISREG(st.st_mode):
        return None, "target.file_not_regular"

    relative = os.path.relpath(resolved, root_real).replace(os.sep, "/")
    secret, rule_id = _secret_rule_match(relative, profile)
    identity = {
        "requested": requested,
        "lexical": lexical,
        "resolved_path": resolved,
        "relative_to_workspace": relative,
        "object_identity": _object_identity(resolved, st),
        "follow_mode": "target",
        "boundary": "workspace",
        "sensitivity": "secret" if secret else "nonsecret",
    }
    target = {
        "role": "input",
        "kind": "secret_file" if secret else "workspace_file",
        "identity": identity,
    }
    if secret and rule_id:
        target["identity"]["secret_rule_id"] = rule_id
    return target, None


def _parse_static_grep(command: str, profile: dict[str, Any]) -> tuple[list[str] | None, str | None]:
    if not isinstance(command, str) or not command:
        return None, "syntax.empty"
    if command != command.strip() or "  " in command:
        return None, "syntax.whitespace_unsupported"
    if any(ch in FORBIDDEN_CHARS for ch in command):
        return None, "syntax.dynamic_or_operator"
    argv = command.split(" ")
    if len(argv) != 3 or any(not token or TOKEN_RE.fullmatch(token) is None for token in argv):
        return None, "grep.shape_unsupported"

    grep_profile = (profile.get("executables") or {}).get("grep") or {}
    expected = grep_profile.get("path")
    if not isinstance(expected, str) or argv[0] != expected:
        return None, "executable.not_allowlisted"
    if argv[1].startswith("-") or argv[2].startswith("-"):
        return None, "grep.options_unsupported"
    if not posixpath.isabs(argv[0]):
        return None, "executable.absolute_path_required"
    return argv, None


def prepare(command: str, cwd: str, workspace_root: str, profile_path: str) -> dict[str, Any]:
    if sys.platform != SUPPORTED_PLATFORM:
        return {"result": _ask("platform.unsupported"), "guard": None}
    try:
        profile = _load_profile(profile_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"result": _ask("profile.invalid"), "guard": None}

    argv, error = _parse_static_grep(command, profile)
    if error:
        return {"result": _ask(error), "guard": None}
    assert argv is not None

    shell_path = (profile.get("shell") or {}).get("path")
    if not isinstance(shell_path, str):
        return {"result": _ask("profile.shell_missing"), "guard": None}
    shell_id, error = _trusted_system_executable(shell_path)
    if error:
        return {"result": _ask(error), "guard": None}

    grep_profile = (profile.get("executables") or {}).get("grep") or {}
    grep_path = grep_profile.get("path")
    semantic_name = grep_profile.get("semantic_name")
    if not isinstance(grep_path, str) or semantic_name != "grep":
        return {"result": _ask("profile.grep_missing"), "guard": None}
    executable, error = _trusted_system_executable(grep_path, semantic_name="grep")
    if error:
        return {"result": _ask(error), "guard": None}

    cwd_id, error = _directory_identity(cwd, workspace_root)
    if error:
        return {"result": _ask(error), "guard": None}

    target, error = _file_target(argv[2], cwd, workspace_root, profile)
    if error:
        return {"result": _ask(error, effects=["process", "read", "search"]), "guard": None}

    assert shell_id and executable and cwd_id and target
    semantic_fact = {
        "schema": FACT_SCHEMA,
        "platform": SUPPORTED_PLATFORM,
        "parser": {
            "status": "exact",
            "profile": profile["classifier_profile_id"],
        },
        "executable": {
            "invoked": "grep",
            "resolved_path": executable["resolved_path"],
            "object_identity": executable["object_identity"],
        },
        "argv": ["grep", argv[1], argv[2]],
        "cwd": copy.deepcopy(cwd_id),
        "targets": [copy.deepcopy(target)],
        "redirects": [],
        "stdin": {"kind": "none"},
    }
    result = analyze_simple(semantic_fact)
    if result["decision"] != "ALLOW":
        return {"result": result, "guard": None}

    exact_operation = copy.deepcopy(result["normalized_operation"])
    exact_operation["execution"]["executable"] = {
        "invoked": executable["invoked"],
        "resolved_path": executable["resolved_path"],
        "object_identity": executable["object_identity"],
    }
    exact_operation["execution"]["argv"] = argv
    exact_result = allow_result(
        exact_operation,
        reason_codes=[*result["reason_codes"], "adapter.p0_exact_grep_binding"],
        classifier_profile_id=profile["classifier_profile_id"],
    )

    target_identity = exact_result["normalized_operation"]["targets"][0]["identity"]
    guard = {
        "schema": GUARD_SCHEMA,
        "classifier_profile_id": profile["classifier_profile_id"],
        "opencode_version": profile["target"]["opencode_version"],
        "compatibility_profile_id": profile["target"]["compatibility_profile_id"],
        "native_policy_artifact_id": profile["target"]["native_policy_artifact_id"],
        "command": command,
        "shell": shell_id,
        "executable": executable,
        "cwd": cwd_id,
        "target": target_identity,
        "operation_identity": exact_result["operation_identity"],
    }
    return {"result": exact_result, "guard": guard}


def revalidate(
    guard: dict[str, Any],
    command: str,
    cwd: str,
    workspace_root: str,
    profile_path: str,
) -> dict[str, Any]:
    if not isinstance(guard, dict) or guard.get("schema") != GUARD_SCHEMA:
        return {"ok": False, "reason": "guard.invalid"}
    if guard.get("command") != command:
        return {"ok": False, "reason": "guard.command_mismatch"}

    fresh = prepare(command, cwd, workspace_root, profile_path)
    result = fresh.get("result") or {}
    fresh_guard = fresh.get("guard")
    if result.get("decision") != "ALLOW" or not isinstance(fresh_guard, dict):
        return {"ok": False, "reason": "guard.revalidation_not_allow"}
    for key in (
        "classifier_profile_id",
        "opencode_version",
        "compatibility_profile_id",
        "native_policy_artifact_id",
        "shell",
        "executable",
        "cwd",
        "target",
        "operation_identity",
    ):
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
    prep.add_argument("--profile", required=True)

    rev = sub.add_parser("revalidate")
    rev.add_argument("--guard-file")
    rev.add_argument("--command", required=True)
    rev.add_argument("--cwd", required=True)
    rev.add_argument("--workspace-root", required=True)
    rev.add_argument("--profile", required=True)

    args = parser.parse_args()
    if args.action == "prepare":
        payload = prepare(args.command, args.cwd, args.workspace_root, args.profile)
    else:
        guard = _read_json(args.guard_file) if args.guard_file else json.load(sys.stdin)
        payload = revalidate(
            guard,
            args.command,
            args.cwd,
            args.workspace_root,
            args.profile,
        )
    json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

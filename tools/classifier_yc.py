#!/usr/bin/env python3
"""Narrow deterministic analyzer for exact, parser-produced YC argv facts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from classifier_core import allow_result, ask_result, deny_result, make_result

POLICY_PATH = Path(__file__).resolve().parents[1] / "policy" / "yc" / "yc_policy.v1.json"
FACT_SCHEMA = "parsed-simple/v1"


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ask(code: str, *, effects: list[str], targets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return ask_result(reason_codes=[code], effects=effects, targets=targets or [], uncertainties=[code])


def _valid_fact(fact: Any) -> bool:
    parser = fact.get("parser") if isinstance(fact, dict) else None
    argv = fact.get("argv") if isinstance(fact, dict) else None
    executable = fact.get("executable") if isinstance(fact, dict) else None
    cwd = fact.get("cwd") if isinstance(fact, dict) else None
    return (
        isinstance(fact, dict)
        and fact.get("schema") == FACT_SCHEMA
        and isinstance(parser, dict)
        and parser.get("status") == "exact"
        and isinstance(argv, list)
        and bool(argv)
        and all(isinstance(item, str) for item in argv)
        and isinstance(executable, dict)
        and executable.get("invoked") == "yc"
        and all(isinstance(executable.get(field), str) and executable[field] for field in ("resolved_path", "object_identity"))
        and isinstance(cwd, dict)
        and all(isinstance(cwd.get(field), str) and cwd[field] for field in ("lexical", "object_identity"))
        and cwd.get("follow_mode") in {"target", "link"}
        and argv[0] == "yc"
    )


def _option_name(token: str) -> str | None:
    if not token.startswith("--"):
        return None
    return token.split("=", 1)[0]


def _native_deny(args: list[str], policy: dict[str, Any]) -> str | None:
    deny = policy["deny"]
    for sequence in deny["guard_denied_sequences"]:
        size = len(sequence)
        if any(args[index:index + size] == sequence for index in range(len(args) - size + 1)):
            return "yc guard approval or uninstall is never authorized"
    sensitive_flags = set(deny["sensitive_flags"])
    if any(_option_name(token) in sensitive_flags for token in args):
        return "credential, profile, endpoint, or impersonation override"
    for sequence in deny["sequences"]:
        size = len(sequence)
        if any(args[index:index + size] == sequence for index in range(len(args) - size + 1)):
            return "credential or secret operation"
    if args[:2] == ["iam", "create-token"] or args[:2] == ["iam", "create-id-token"]:
        return "token creation"
    if len(args) >= 3 and args[:2] == ["config", "get"]:
        key = args[2].lower()
        if any(part in key for part in deny["sensitive_config_keys"]):
            return "sensitive config read"
    if len(args) >= 3 and args[:2] == ["iam", "key"] and args[2] not in {"list", "get"}:
        return "key material operation"
    if args[:3] == ["iam", "key", "get"]:
        return "key material read"
    return None


def _target(service: str, resource_type: str, resource_id: str | None = None) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "provider": "yandex-cloud",
        "service": service,
        "resource_type": resource_type,
    }
    if resource_id is not None:
        identity["resource_id"] = resource_id
    return {"role": "cloud_resource", "kind": "cloud_resource", "identity": identity}


def _operation(fact: dict[str, Any], targets: list[dict[str, Any]], effects: list[str]) -> dict[str, Any]:
    return {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": fact["platform"],
        "channel": "local",
        "operation_kind": "process_exec",
        "execution": {
            "kind": "argv",
            "executable": copy.deepcopy(fact["executable"]),
            "argv": list(fact["argv"]),
            "cwd": copy.deepcopy(fact["cwd"]),
        },
        "targets": copy.deepcopy(targets),
        "effects": effects,
        "context_dependencies": [],
    }


def _parsed_command(args: list[str]) -> tuple[str, str, str, list[str]] | None:
    if len(args) < 3 or any(token.startswith("-") for token in args[:3]):
        return None
    return args[0], args[1], args[2], args[3:]


def _id_value(rest: list[str]) -> str | None:
    if rest.count("--id") != 1 or any(token.startswith("--id=") for token in rest):
        return None
    index = rest.index("--id")
    if index + 1 >= len(rest) or rest[index + 1].startswith("-"):
        return None
    return rest[index + 1]


def analyze_yc(fact: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify one exact parsed-simple/v1 YC fact without executing YC."""
    if not _valid_fact(fact):
        return _ask("input.invalid_yc_fact", effects=["process", "unknown"])
    policy = policy or load_policy()
    args = list(fact["argv"][1:])
    denied = _native_deny(args, policy)
    if denied:
        return deny_result(reason_codes=["yc.hard_deny"], effects=["process", "network", "secrets"], targets=[])

    parsed = _parsed_command(args)
    if parsed is None:
        return _ask("yc.syntax.opaque", effects=["process", "network", "unknown"])
    service, resource, action, rest = parsed
    resource_type = f"{service}.{resource}"
    target_id = _id_value(rest)
    target_name = rest[rest.index("--name") + 1] if rest.count("--name") == 1 and rest.index("--name") + 1 < len(rest) else None
    target = _target(service, resource_type, target_id or target_name)

    exact_read = any(
        item.get("service") == service
        and item.get("resource") == resource
        and item.get("action") == action
        and (item.get("argv", [])[1:] == args or (item.get("argv", [])[1:][-2:] == ["--id", "<resource_id>"] and rest == ["--id", target_id]))
        for item in policy.get("allow_read", [])
    )
    exact_mutation = any(
        item.get("service") == service
        and item.get("resource") == resource
        and item.get("action") == action
        and item.get("resource_id") == target_id
        and item.get("argv") == list(fact["argv"])
        for item in policy.get("allow_mutations", [])
    )
    if exact_read:
        operation = _operation(fact, [target], ["process", "network", "cloud_read"])
        return allow_result(operation, reason_codes=["yc.policy.exact_read"], classifier_profile_id="yc-v1")
    if exact_mutation:
        effects = ["process", "network", "cloud_state_change"]
        operation = _operation(fact, [target], effects)
        return allow_result(operation, reason_codes=["yc.policy.exact_mutation"], classifier_profile_id="yc-v1")

    effects = ["process", "network"]
    if service == "iam":
        effects.extend(["cloud_read", "iam"])
    elif action in {"list", "get", "describe", "status"}:
        effects.append("cloud_read")
    else:
        effects.append("cloud_state_change")
    operation = _operation(fact, [target], effects)
    return make_result(
        "ASK_USER",
        reason_codes=["yc.policy.not_exact_allow"],
        effects=operation["effects"],
        targets=operation["targets"],
        uncertainties=["yc.policy.not_exact_allow"],
        normalized_operation=operation,
        classifier_profile_id="yc-v1",
    )


def analyze(fact: dict[str, Any], native_decision: str | None = None) -> dict[str, Any]:
    """Compatibility entry point for the analyzer, not a second dispatcher."""
    if native_decision == "DENY":
        return deny_result(reason_codes=["native.hard_deny_terminal"], effects=["process"])
    return analyze_yc(fact)

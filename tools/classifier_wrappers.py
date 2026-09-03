#!/usr/bin/env python3
"""DC-3 deterministic wrapper/remote extraction over exact outer argv facts.

This module does not parse raw shell text. Local wrapper argv boundaries are assumed
to come from an exact parser adapter. Remote command strings stay non-ALLOW unless
an exact nested remote fact is supplied; even then remote/wrapper paths remain ASK
unless a hard DENY is proven.
"""
from __future__ import annotations

import copy
from typing import Any, Iterable

from classifier_analyzers import analyze_simple
from classifier_core import ask_result, deny_result, make_result
from normalized_operation_identity import jcs_dumps

FACT_SCHEMA = "parsed-wrapper/v1"
EXACT = "exact"
SELF_APPROVAL_FLAGS = {"--approved", "--allow-critical"}
AGENT_SAFE_CHANGE_COMMANDS = {
    "exec-risky",
    "system-change",
    "yc-change",
    "ssh-relay-risky",
}
AGENT_SAFE_REMAINDER_COMMANDS = {
    "exec-risky",
    "exec-readonly",
    "system-change",
    "system-readonly",
    "yc-change",
    "yc-readonly",
}
AGENT_SAFE_POLICY_MUTATION = {"opencode-bootstrap"}
SSH_RELAY_READ_CONTROL = {"status", "list"}
SSH_RELAY_JOB_READ = {"status", "list", "wait", "tail"}


def _ask(code: str, *, effects: Iterable[str] = ("unknown",), targets: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    return ask_result(
        reason_codes=[code],
        effects=effects,
        targets=targets,
        uncertainties=[code],
    )


def _valid_executable(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("invoked"), str)
        and bool(value["invoked"])
        and isinstance(value.get("resolved_path"), str)
        and bool(value["resolved_path"])
        and isinstance(value.get("object_identity"), str)
        and bool(value["object_identity"])
    )


def _valid_cwd(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("lexical"), str)
        and bool(value["lexical"])
        and isinstance(value.get("object_identity"), str)
        and bool(value["object_identity"])
        and value.get("follow_mode") in {"target", "link"}
    )


def _target_valid(target: Any) -> bool:
    return (
        isinstance(target, dict)
        and isinstance(target.get("role"), str)
        and bool(target["role"])
        and isinstance(target.get("kind"), str)
        and bool(target["kind"])
        and isinstance(target.get("identity"), dict)
    )


def _targets(fact: dict[str, Any]) -> list[dict[str, Any]]:
    values = fact.get("targets", [])
    if not isinstance(values, list) or not all(_target_valid(item) for item in values):
        return []
    return copy.deepcopy(values)


def _merge_targets(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            if _target_valid(item):
                by_key[jcs_dumps(item)] = copy.deepcopy(item)
    return [by_key[key] for key in sorted(by_key)]


def _merge_effects(*groups: Iterable[str]) -> list[str]:
    return sorted({item for group in groups for item in group})


def _base_valid(fact: Any) -> bool:
    if not isinstance(fact, dict) or fact.get("schema") != FACT_SCHEMA:
        return False
    parser = fact.get("parser")
    argv = fact.get("argv")
    return (
        isinstance(parser, dict)
        and parser.get("status") == EXACT
        and isinstance(argv, list)
        and bool(argv)
        and all(isinstance(item, str) for item in argv)
        and _valid_executable(fact.get("executable"))
        and _valid_cwd(fact.get("cwd"))
        and argv[0] == fact["executable"]["invoked"]
    )


def _split_delimiter(argv: list[str]) -> tuple[list[str], list[str] | None]:
    if "--" not in argv:
        return list(argv), None
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def _nested_bound(fact: dict[str, Any], payload: list[str] | None, field: str = "payload_fact") -> dict[str, Any] | None:
    nested = fact.get(field)
    if not isinstance(nested, dict) or payload is None:
        return None
    if nested.get("schema") != "parsed-simple/v1":
        return None
    if nested.get("argv") != payload:
        return None
    return nested


def _child_for_remainder(fact: dict[str, Any], argv_after_subcommand: list[str]) -> dict[str, Any] | None:
    _prefix, payload = _split_delimiter(argv_after_subcommand)
    if payload is None or not payload:
        return None
    return _nested_bound(fact, payload)


def _child_dominates(
    child: dict[str, Any] | None,
    *,
    outer_effects: Iterable[str],
    outer_targets: Iterable[dict[str, Any]],
    ask_code: str,
) -> dict[str, Any]:
    if child is None:
        return _ask(
            ask_code,
            effects=_merge_effects(outer_effects, ["unknown_code_execution"]),
            targets=outer_targets,
        )
    result = analyze_simple(copy.deepcopy(child))
    effects = _merge_effects(outer_effects, result["effects"])
    targets = _merge_targets(outer_targets, result["targets"])
    if result["decision"] == "DENY":
        return deny_result(
            reason_codes=[ask_code, "wrapper.child_deny"],
            effects=effects,
            targets=targets,
        )
    uncertainties = list(result.get("uncertainties", []))
    uncertainties.append(ask_code)
    return ask_result(
        reason_codes=[ask_code, "wrapper.authorization_required"],
        effects=effects,
        targets=targets,
        uncertainties=uncertainties,
    )


def _safe_invocation(argv: list[str]) -> tuple[str, list[str]] | None:
    if argv[0] == "safe":
        rest = list(argv[1:])
    elif (
        argv[0] in {"python", "python3"}
        and len(argv) >= 4
        and argv[1:3] == ["-m", "agent_safe"]
    ):
        rest = list(argv[3:])
    else:
        return None

    while len(rest) >= 2 and rest[0] == "--root":
        rest = rest[2:]
    if not rest:
        return None
    return rest[0], rest[1:]


def _analyze_agent_safe(fact: dict[str, Any], subcommand: str, args: list[str]) -> dict[str, Any]:
    outer_targets = _targets(fact)
    prefix, _ = _split_delimiter(args)
    if SELF_APPROVAL_FLAGS.intersection(prefix):
        return deny_result(
            reason_codes=["agent_safe.self_approval"],
            effects=["process", "wrapper", "approval_substitution"],
            targets=outer_targets,
        )

    if subcommand == "opencode-bootstrap":
        if "--apply" in args:
            return deny_result(
                reason_codes=["agent_safe.policy_mutation"],
                effects=["process", "wrapper", "authorization_policy_mutation", "write"],
                targets=outer_targets,
            )
        return _ask(
            "agent_safe.bootstrap_review",
            effects=["process", "wrapper", "read"],
            targets=outer_targets,
        )

    if subcommand in AGENT_SAFE_REMAINDER_COMMANDS:
        child = _child_for_remainder(fact, args)
        effects = ["process", "wrapper", "controlled_path"]
        if subcommand in AGENT_SAFE_CHANGE_COMMANDS:
            effects.append("write")
        return _child_dominates(
            child,
            outer_effects=effects,
            outer_targets=outer_targets,
            ask_code="agent_safe.controlled_path",
        )

    if subcommand == "ssh-relay-risky":
        remote_child = fact.get("remote_payload_fact")
        if isinstance(remote_child, dict):
            result = analyze_simple(copy.deepcopy(remote_child))
            if result["decision"] == "DENY":
                return deny_result(
                    reason_codes=["agent_safe.remote_child_deny"],
                    effects=_merge_effects(
                        ["process", "wrapper", "network", "remote_execution", "remote_state_change"],
                        result["effects"],
                    ),
                    targets=_merge_targets(outer_targets, result["targets"]),
                )
        return _ask(
            "agent_safe.remote_controlled_path",
            effects=["process", "wrapper", "network", "remote_execution", "remote_state_change"],
            targets=outer_targets,
        )

    if subcommand in {"fs-move", "fs-trash", "undo", "redo", "checkpoint", "git-checkpoint"}:
        return _ask(
            "agent_safe.stateful_operation",
            effects=["process", "wrapper", "write"],
            targets=outer_targets,
        )

    if subcommand in {"status", "diagnose", "recovery-plan", "git-clean-preview", "assess"}:
        return _ask(
            "agent_safe.read_control",
            effects=["process", "wrapper", "read"],
            targets=outer_targets,
        )

    return _ask(
        "agent_safe.subcommand_unknown",
        effects=["process", "wrapper", "unknown"],
        targets=outer_targets,
    )


def _remote_host_target(fact: dict[str, Any]) -> dict[str, Any] | None:
    remote = fact.get("remote")
    if not isinstance(remote, dict):
        return None
    host_identity = remote.get("host_identity")
    if not isinstance(host_identity, str) or not host_identity:
        return None
    return {
        "role": "host",
        "kind": "host",
        "identity": {"canonical": host_identity},
    }


def _remote_payload_child(fact: dict[str, Any], raw: str) -> dict[str, Any] | None:
    envelope = fact.get("remote_payload")
    if not isinstance(envelope, dict):
        return None
    if envelope.get("status") != "exact" or envelope.get("source_text") != raw:
        return None
    nested = envelope.get("fact")
    if not isinstance(nested, dict) or nested.get("schema") != "parsed-simple/v1":
        return None
    return nested


def _remote_exec_decision(
    fact: dict[str, Any],
    raw: str,
    *,
    risky: bool,
    job: bool = False,
) -> dict[str, Any]:
    host = _remote_host_target(fact)
    targets = _merge_targets(_targets(fact), [host] if host else [])
    base = ["process", "network", "remote_execution"]
    if risky:
        base.extend(["risk_label", "remote_state_change"])
    if job:
        base.append("remote_job")
    if host is None:
        return _ask(
            "ssh_relay.host_identity_missing",
            effects=_merge_effects(base, ["unknown"]),
            targets=targets,
        )

    child = _remote_payload_child(fact, raw)
    if child is None:
        return _ask(
            "ssh_relay.remote_shell_unproven",
            effects=_merge_effects(base, ["unknown_code_execution"]),
            targets=targets,
        )
    result = analyze_simple(copy.deepcopy(child))
    effects = _merge_effects(base, result["effects"])
    targets = _merge_targets(targets, result["targets"])
    if result["decision"] == "DENY":
        return deny_result(
            reason_codes=["ssh_relay.remote_child_deny"],
            effects=effects,
            targets=targets,
        )
    return ask_result(
        reason_codes=["ssh_relay.remote_authorization_required"],
        effects=effects,
        targets=targets,
        uncertainties=["ssh_relay.remote_shell_boundary"],
    )


def _transfer_operation(
    fact: dict[str, Any],
    *,
    direction: str,
    overwrite: bool,
) -> dict[str, Any] | None:
    host = _remote_host_target(fact)
    remote = fact.get("remote")
    targets = _targets(fact)
    if host is None or not isinstance(remote, dict):
        return None
    roles = {item["role"] for item in targets}
    if not {"source", "destination"}.issubset(roles):
        return None
    effects = (
        ["network", "transfer", "remote_write", "remote_state_change"]
        if direction == "upload"
        else ["network", "transfer", "local_write"]
    )
    return {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": fact["platform"],
        "channel": "transfer",
        "operation_kind": "transfer",
        "execution": {
            "kind": "transfer",
            "transport": "ssh_relay",
            "direction": direction,
            "overwrite": "replace" if overwrite else "fail_if_exists",
        },
        "remote": {
            "transport": "ssh_relay",
            "host_identity": remote["host_identity"],
        },
        "targets": copy.deepcopy(targets),
        "effects": effects,
        "context_dependencies": [],
    }


def _analyze_ssh_relay(fact: dict[str, Any], args: list[str]) -> dict[str, Any]:
    if not args:
        return _ask("ssh_relay.subcommand_missing", effects=["process", "network", "unknown"])
    subcommand = args[0]
    subargs = args[1:]
    targets = _targets(fact)

    if subcommand == "sudo-exec":
        return deny_result(
            reason_codes=["ssh_relay.privilege"],
            effects=["process", "network", "remote_execution", "privilege", "remote_state_change"],
            targets=targets,
        )

    if subcommand == "exec":
        if not subargs:
            return _ask("ssh_relay.exec_shape_unknown", effects=["process", "network", "remote_execution"])
        raw = fact.get("remote_command")
        if not isinstance(raw, str) or not raw:
            return _ask("ssh_relay.remote_command_missing", effects=["process", "network", "remote_execution"])
        risky = "--risky" in subargs
        return _remote_exec_decision(fact, raw, risky=risky)

    if subcommand in {"upload", "download"}:
        operation = _transfer_operation(
            fact,
            direction=subcommand,
            overwrite="--overwrite" in subargs,
        )
        effects = (
            ["network", "transfer", "remote_write", "remote_state_change"]
            if subcommand == "upload"
            else ["network", "transfer", "local_write"]
        )
        if operation is None:
            return _ask(
                "ssh_relay.transfer_identity_missing",
                effects=_merge_effects(effects, ["unknown"]),
                targets=targets,
            )
        return make_result(
            "ASK_USER",
            reason_codes=["ssh_relay.transfer_authorization_required"],
            effects=effects,
            targets=operation["targets"],
            uncertainties=["transfer.approval_required"],
            normalized_operation=operation,
            classifier_profile_id="dc3-wrapper-remote-v1",
        )

    if subcommand == "job":
        if not subargs:
            return _ask("ssh_relay.job_shape_unknown", effects=["process", "network", "remote_job"])
        job_command = subargs[0]
        if job_command == "start":
            raw = fact.get("remote_command")
            if not isinstance(raw, str) or not raw:
                return _ask(
                    "ssh_relay.job_payload_missing",
                    effects=["process", "network", "remote_execution", "remote_job", "unknown_code_execution"],
                )
            return _remote_exec_decision(fact, raw, risky=False, job=True)
        if job_command in SSH_RELAY_JOB_READ:
            effects = ["process", "network", "remote_job", "read"]
            if job_command == "tail":
                effects.append("possible_sensitive_output")
            return _ask(
                "ssh_relay.job_read_control",
                effects=effects,
                targets=targets,
            )
        if job_command == "stop":
            return _ask(
                "ssh_relay.job_process_control",
                effects=["process", "network", "remote_job", "process_control", "remote_state_change"],
                targets=targets,
            )
        return _ask(
            "ssh_relay.job_unknown",
            effects=["process", "network", "remote_job", "unknown"],
            targets=targets,
        )

    if subcommand in SSH_RELAY_READ_CONTROL:
        return _ask(
            "ssh_relay.read_control",
            effects=["process", "network", "read", "remote_status"],
            targets=targets,
        )

    if subcommand in {"daemon", "stop"}:
        return _ask(
            "ssh_relay.lifecycle_control",
            effects=["process", "network", "process_control"],
            targets=targets,
        )

    return _ask(
        "ssh_relay.subcommand_unknown",
        effects=["process", "network", "unknown"],
        targets=targets,
    )


def analyze_wrapper(fact: dict[str, Any]) -> dict[str, Any]:
    if not _base_valid(fact):
        if isinstance(fact, dict) and fact.get("schema") == FACT_SCHEMA:
            parser = fact.get("parser")
            if not isinstance(parser, dict) or parser.get("status") != EXACT:
                return _ask("syntax.opaque")
        return _ask("input.invalid_wrapper_fact")

    argv = list(fact["argv"])
    safe = _safe_invocation(argv)
    if safe is not None:
        return _analyze_agent_safe(fact, safe[0], safe[1])

    if argv[0] == "ssh_relay":
        return _analyze_ssh_relay(fact, argv[1:])

    return _ask(
        "wrapper.unknown",
        effects=["process", "wrapper", "unknown"],
        targets=_targets(fact),
    )

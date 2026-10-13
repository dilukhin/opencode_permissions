#!/usr/bin/env python3
"""DC-3 deterministic wrapper/remote extraction over exact outer argv facts.

This module does not parse raw shell text. Local wrapper argv boundaries are assumed
to come from an exact parser adapter. Remote command strings stay non-ALLOW unless
an exact nested remote fact is supplied; even then remote/wrapper paths remain ASK
unless a hard DENY is proven.
"""
from __future__ import annotations

import copy
import hashlib
import re
import uuid
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



_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}\Z")
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SUDO_JOB_BINDING_FIELDS = {
    "job_id", "transaction_id", "command_sha256", "identity_file_path",
    "identity_file_object_identity", "verified_identity",
}
_VERIFIED_IDENTITY_FIELDS = {
    "remote_host", "remote_port", "remote_user", "host_key_algorithm",
    "remote_host_key_sha256", "daemon_instance_id", "connection_generation",
    "daemon_source_sha",
}


def _flag_once(args: list[str], name: str) -> str | None:
    positions = [index for index, value in enumerate(args) if value == name]
    if len(positions) != 1:
        return None
    index = positions[0]
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _canonical_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None
    return parsed if parsed == value else None


def _sudo_job_cli_valid(args: list[str], operation: str, raw: str | None) -> bool:
    """Разбирает только проверенные полные формы CLI; прочие остаются ASK."""
    options = {"--name", "-n", "--job-id", "--transaction-id", "--expected-identity-file"}
    if operation != "start":
        options.add("--command-sha256")
    if operation == "tail":
        options.update({"--stream", "--bytes"})
    if operation == "wait":
        options.update({"--timeout", "--poll-interval"})
    seen: dict[str, str] = {}
    positionals: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            positionals.extend(args[index + 1:])
            break
        if token in options:
            key = "--name" if token == "-n" else token
            if key in seen or index + 1 >= len(args) or not args[index + 1] or args[index + 1].startswith("-"):
                return False
            seen[key] = args[index + 1]
            index += 2
            continue
        if token.startswith("-"):
            return False
        positionals.append(token)
        index += 1
    required = {"--job-id", "--transaction-id", "--expected-identity-file"}
    if operation != "start":
        required.add("--command-sha256")
    if not required.issubset(seen):
        return False
    if positionals != ([raw] if operation == "start" else []):
        return False
    if "--stream" in seen and seen["--stream"] not in {"stdout", "stderr"}:
        return False
    for key, maximum in (("--bytes", 65536), ("--timeout", 86400), ("--poll-interval", 60)):
        if key in seen:
            try:
                if not 1 <= int(seen[key]) <= maximum:
                    return False
            except ValueError:
                return False
    return True


def _trusted_sudo_job_binding(
    fact: dict[str, Any],
    subargs: list[str],
    operation: str,
    remote_command: str | None,
) -> dict[str, Any] | None:
    if not _sudo_job_cli_valid(subargs, operation, remote_command):
        return None
    envelope = fact.get("sudo_job_identity")
    if not isinstance(envelope, dict) or envelope.get("status") != EXACT:
        return None
    value = envelope.get("value")
    if not isinstance(value, dict) or set(value) != _SUDO_JOB_BINDING_FIELDS:
        return None
    job_id = _canonical_uuid(value.get("job_id"))
    transaction_id = _canonical_uuid(value.get("transaction_id"))
    command_sha256 = value.get("command_sha256")
    identity_path = value.get("identity_file_path")
    identity_object = value.get("identity_file_object_identity")
    verified = value.get("verified_identity")
    if (
        job_id is None
        or transaction_id is None
        or not isinstance(command_sha256, str)
        or _SHA256.fullmatch(command_sha256) is None
        or not isinstance(identity_path, str)
        or not identity_path
        or not isinstance(identity_object, str)
        or not identity_object
        or not isinstance(verified, dict)
        or set(verified) != _VERIFIED_IDENTITY_FIELDS
    ):
        return None
    if (
        not isinstance(verified.get("remote_host"), str)
        or not verified["remote_host"]
        or type(verified.get("remote_port")) is not int
        or not 1 <= verified["remote_port"] <= 65535
        or not isinstance(verified.get("remote_user"), str)
        or not verified["remote_user"]
        or not isinstance(verified.get("host_key_algorithm"), str)
        or not verified["host_key_algorithm"]
        or not isinstance(verified.get("remote_host_key_sha256"), str)
        or _FINGERPRINT.fullmatch(verified["remote_host_key_sha256"]) is None
        or _canonical_uuid(verified.get("daemon_instance_id")) is None
        or type(verified.get("connection_generation")) is not int
        or verified["connection_generation"] < 1
        or not isinstance(verified.get("daemon_source_sha"), str)
        or _SOURCE_SHA.fullmatch(verified["daemon_source_sha"]) is None
    ):
        return None
    if (
        _flag_once(subargs, "--job-id") != job_id
        or _flag_once(subargs, "--transaction-id") != transaction_id
        or _flag_once(subargs, "--expected-identity-file") != identity_path
    ):
        return None
    if operation == "start":
        if not isinstance(remote_command, str):
            return None
        actual_hash = hashlib.sha256(remote_command.encode("utf-8")).hexdigest()
        if actual_hash != command_sha256:
            return None
    elif _flag_once(subargs, "--command-sha256") != command_sha256:
        return None
    return {
        "job_id": job_id,
        "transaction_id": transaction_id,
        "command_sha256": command_sha256,
        "identity_file_path": identity_path,
        "identity_file_object_identity": identity_object,
        "verified_identity": copy.deepcopy(verified),
    }


def _sudo_job_operation(
    fact: dict[str, Any],
    subargs: list[str],
    operation: str,
    remote_command: str | None,
    effects: list[str],
) -> dict[str, Any] | None:
    binding = _trusted_sudo_job_binding(fact, subargs, operation, remote_command)
    host = _remote_host_target(fact)
    remote = fact.get("remote")
    if binding is None or host is None or not isinstance(remote, dict):
        return None
    targets = _merge_targets(
        _targets(fact),
        [host, {
            "role": "job",
            "kind": "remote_job",
            "identity": {"canonical": binding["job_id"]},
        }],
    )
    verified = binding["verified_identity"]
    dependency = {
        "kind": "ssh_relay_verified_identity",
        "source_path": binding["identity_file_path"],
        "source_object_identity": binding["identity_file_object_identity"],
        **verified,
    }
    return {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": fact["platform"],
        "channel": "remote",
        "operation_kind": "remote_exec",
        "execution": {
            "kind": "remote_argv",
            "argv": [
                "ssh_relay:sudo-job",
                operation,
                binding["job_id"],
                binding["transaction_id"],
                binding["command_sha256"],
            ],
            "transport": "ssh_relay",
            "sudo_job_operation": operation,
            "job_id": binding["job_id"],
            "transaction_id": binding["transaction_id"],
            "command_sha256": binding["command_sha256"],
            "privilege": "root",
            # Несекретный hash связывает весь внешний вызов, включая relay
            # session, лимиты чтения/ожидания, executable и рабочий каталог.
            "relay_invocation_sha256": hashlib.sha256(jcs_dumps({
                "argv": fact["argv"],
                "executable": fact["executable"],
                "cwd": fact["cwd"],
            }).encode("utf-8")).hexdigest(),
        },
        "remote": {
            "transport": "ssh_relay",
            "host_identity": remote["host_identity"],
        },
        "targets": targets,
        "effects": effects,
        "context_dependencies": [dependency],
    }


def _sudo_job_decision(fact: dict[str, Any], subargs: list[str]) -> dict[str, Any]:
    targets = _targets(fact)
    if not subargs:
        return _ask(
            "ssh_relay.sudo_job_shape_unknown",
            effects=["process", "network", "remote_job", "privilege", "unknown"],
            targets=targets,
        )
    operation = subargs[0]
    command_args = subargs[1:]
    if operation not in {"start", "status", "tail", "wait", "stop"}:
        return _ask(
            "ssh_relay.sudo_job_unknown",
            effects=["process", "network", "remote_job", "privilege", "unknown"],
            targets=targets,
        )

    raw = fact.get("remote_command") if operation == "start" else None
    child = None
    effects = ["process", "network", "remote_job"]
    if operation == "start":
        effects.extend(["remote_execution", "privilege", "remote_state_change"])
        if not isinstance(raw, str) or not raw:
            return _ask(
                "ssh_relay.sudo_job_payload_missing",
                effects=_merge_effects(effects, ["unknown_code_execution"]),
                targets=targets,
            )
        child = _remote_payload_child(fact, raw)
        if child is None:
            return _ask(
                "ssh_relay.sudo_job_remote_shell_unproven",
                effects=_merge_effects(effects, ["unknown_code_execution"]),
                targets=targets,
            )
        nested = analyze_simple(copy.deepcopy(child))
        effects = _merge_effects(effects, nested["effects"])
        targets = _merge_targets(targets, nested["targets"])
        if nested["decision"] == "DENY":
            return deny_result(
                reason_codes=["ssh_relay.sudo_job_remote_child_deny"],
                effects=effects,
                targets=targets,
            )
    elif operation in {"status", "wait", "tail"}:
        effects.extend(["read", "remote_status"])
        if operation == "tail":
            effects.append("possible_sensitive_output")
    else:
        effects.extend(["privilege", "process_control", "remote_state_change"])

    normalized = _sudo_job_operation(fact, command_args, operation, raw, effects)
    if normalized is None:
        return _ask(
            "ssh_relay.sudo_job_binding_missing_or_mismatch",
            effects=_merge_effects(effects, ["unknown"]),
            targets=targets,
        )
    reason = (
        "ssh_relay.sudo_job_start_authorization_required"
        if operation == "start"
        else "ssh_relay.sudo_job_stop_authorization_required"
        if operation == "stop"
        else "ssh_relay.sudo_job_read_control"
    )
    return make_result(
        "ASK_USER",
        reason_codes=[reason],
        effects=effects,
        targets=normalized["targets"],
        uncertainties=["ssh_relay.sudo_job_human_authorization_required"],
        normalized_operation=normalized,
        classifier_profile_id="sudo-job-v1",
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

    if subcommand == "sudo-job":
        return _sudo_job_decision(fact, subargs)

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

#!/usr/bin/env python3
"""Pure deterministic classifier result/composition core (DC-1).

This module contains no shell parser and no command-specific analyzers. It
validates classifier results, enforces native terminal precedence, and composes
already-classified child operations monotonically.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from normalized_operation_identity import (
    IdentityError,
    extract_identity_core,
    jcs_dumps,
    operation_identity,
)

RESULT_SCHEMA = "classifier-result/v1"
DECISIONS = {"ALLOW", "ASK_USER", "DENY"}
NATIVE_DECISIONS = {"allow", "ask", "deny"}
UNKNOWN_EFFECTS = {"unknown", "unknown_code_execution"}
UNKNOWN_TARGET_KINDS = {"unknown_target"}
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
IDENTITY_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ClassifierError(ValueError):
    def __init__(self, code: str, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise ClassifierError(code, detail)


def _codes(values: Iterable[str], field: str) -> list[str]:
    result = []
    for value in values:
        _require(isinstance(value, str) and CODE_RE.fullmatch(value), f"INVALID_{field.upper()}_CODE", value)
        result.append(value)
    return sorted(set(result))


def _effects(values: Iterable[str]) -> list[str]:
    result = []
    for value in values:
        _require(isinstance(value, str) and CODE_RE.fullmatch(value), "INVALID_EFFECT", value)
        result.append(value)
    return sorted(set(result))


def _canonical_set(values: Iterable[Any]) -> list[Any]:
    by_key: dict[str, Any] = {}
    for value in values:
        key = jcs_dumps(value)
        by_key[key] = value
    return [by_key[key] for key in sorted(by_key)]


def _targets(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for target in values:
        _require(isinstance(target, dict), "INVALID_TARGET")
        _require(isinstance(target.get("role"), str) and target["role"], "TARGET_ROLE_REQUIRED")
        _require(isinstance(target.get("kind"), str) and target["kind"], "TARGET_KIND_REQUIRED")
        _require(isinstance(target.get("identity"), dict), "TARGET_IDENTITY_REQUIRED")
        result.append(target)
    return _canonical_set(result)


def _path_identity_complete(value: Any, *, allow_null_object: bool = False) -> bool:
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("lexical"), str) or not value["lexical"]:
        return False
    if value.get("follow_mode") not in {"target", "link"}:
        return False
    obj = value.get("object_identity")
    if allow_null_object and obj is None:
        return True
    return isinstance(obj, str) and bool(obj)


def validate_operation_completeness(operation: dict[str, Any]) -> dict[str, Any]:
    """Require operation-kind-specific fields before an operation may back ALLOW."""
    try:
        core = extract_identity_core(operation)
    except IdentityError as exc:
        raise ClassifierError("IDENTITY_CORE_INVALID", {"identity_error": exc.code}) from exc

    kind = core["operation_kind"]
    execution = core["execution"]
    ekind = execution.get("kind")

    if kind == "process_exec":
        _require(ekind == "argv", "OPERATION_EXECUTION_KIND_MISMATCH")
        executable = execution.get("executable")
        _require(isinstance(executable, dict), "EXECUTABLE_IDENTITY_REQUIRED")
        for field in ("invoked", "resolved_path", "object_identity"):
            _require(isinstance(executable.get(field), str) and executable[field], f"EXECUTABLE_{field.upper()}_REQUIRED")
        argv = execution.get("argv")
        _require(isinstance(argv, list) and argv, "ARGV_REQUIRED")
        _require(all(isinstance(item, str) for item in argv), "INVALID_ARGV")
        _require(argv[0] == executable["invoked"], "ARGV_EXECUTABLE_MISMATCH")
        _require(_path_identity_complete(execution.get("cwd")), "CWD_IDENTITY_REQUIRED")

    elif kind == "shell_script":
        _require(ekind == "shell_script", "OPERATION_EXECUTION_KIND_MISMATCH")
        shell = execution.get("shell")
        _require(isinstance(shell, dict), "SHELL_IDENTITY_REQUIRED")
        for field in ("resolved_path", "object_identity"):
            _require(isinstance(shell.get(field), str) and shell[field], f"SHELL_{field.upper()}_REQUIRED")
        _require(isinstance(execution.get("script"), str) and execution["script"], "SCRIPT_REQUIRED")
        _require(_path_identity_complete(execution.get("cwd")), "CWD_IDENTITY_REQUIRED")

    elif kind == "remote_exec":
        _require(ekind == "remote_argv", "OPERATION_EXECUTION_KIND_MISMATCH")
        argv = execution.get("argv")
        _require(isinstance(argv, list) and argv and all(isinstance(item, str) for item in argv), "ARGV_REQUIRED")
        remote = core.get("remote")
        _require(isinstance(remote, dict), "REMOTE_IDENTITY_REQUIRED")
        _require(isinstance(remote.get("host_identity"), str) and remote["host_identity"], "REMOTE_HOST_IDENTITY_REQUIRED")
        host_targets = [t for t in core["targets"] if t["role"] == "host" and t["kind"] == "host"]
        _require(host_targets, "REMOTE_HOST_TARGET_REQUIRED")
        _require(
            any(t["identity"].get("canonical") == remote["host_identity"] for t in host_targets),
            "REMOTE_HOST_TARGET_MISMATCH",
        )

    elif kind == "transfer":
        _require(ekind == "transfer", "OPERATION_EXECUTION_KIND_MISMATCH")
        _require(execution.get("direction") in {"upload", "download"}, "TRANSFER_DIRECTION_REQUIRED")
        _require(execution.get("overwrite") in {"replace", "fail_if_exists"}, "TRANSFER_OVERWRITE_MODE_REQUIRED")
        remote = core.get("remote")
        _require(isinstance(remote, dict), "REMOTE_IDENTITY_REQUIRED")
        _require(isinstance(remote.get("host_identity"), str) and remote["host_identity"], "REMOTE_HOST_IDENTITY_REQUIRED")
        roles = {target["role"] for target in core["targets"]}
        _require({"source", "destination"}.issubset(roles), "TRANSFER_TARGETS_REQUIRED")

    elif kind == "file_create":
        _require(ekind == "structured_file_create", "OPERATION_EXECUTION_KIND_MISMATCH")
        destinations = [t for t in core["targets"] if t["role"] == "destination" and t["kind"] == "file"]
        _require(len(destinations) == 1, "FILE_CREATE_DESTINATION_REQUIRED")
        ident = destinations[0]["identity"]
        _require(_path_identity_complete(ident, allow_null_object=True), "FILE_CREATE_PATH_IDENTITY_REQUIRED")
        _require(ident.get("object_identity") is None, "FILE_CREATE_EXISTING_OBJECT_UNEXPECTED")
        _require(isinstance(ident.get("parent_object_identity"), str) and ident["parent_object_identity"], "FILE_CREATE_PARENT_IDENTITY_REQUIRED")
        _require(isinstance(ident.get("leaf"), str) and ident["leaf"], "FILE_CREATE_LEAF_REQUIRED")

    elif kind == "compound":
        _require(ekind == "compound", "OPERATION_EXECUTION_KIND_MISMATCH")
        steps = execution.get("steps")
        operators = execution.get("operators")
        _require(isinstance(steps, list) and len(steps) >= 2, "COMPOUND_STEPS_REQUIRED")
        _require(all(isinstance(item, str) and IDENTITY_RE.fullmatch(item) for item in steps), "INVALID_COMPOUND_STEP_IDENTITY")
        _require(isinstance(operators, list) and len(operators) == len(steps) - 1, "COMPOUND_OPERATORS_REQUIRED")
        _require(all(item in {"&&", "||", ";"} for item in operators), "INVALID_COMPOUND_OPERATOR")

    elif kind == "pipeline":
        _require(ekind == "pipeline", "OPERATION_EXECUTION_KIND_MISMATCH")
        stages = execution.get("stages")
        _require(isinstance(stages, list) and len(stages) >= 2, "PIPELINE_STAGES_REQUIRED")
        _require(all(isinstance(item, str) and IDENTITY_RE.fullmatch(item) for item in stages), "INVALID_PIPELINE_STAGE_IDENTITY")
        pipes = execution.get("pipes")
        _require(isinstance(pipes, list) and len(pipes) == len(stages) - 1, "PIPELINE_OPERATORS_REQUIRED")
        _require(all(item in {"|", "|&"} for item in pipes), "INVALID_PIPELINE_OPERATOR")

    else:
        raise ClassifierError("UNSUPPORTED_OPERATION_KIND", kind)

    return core


def make_result(
    decision: str,
    *,
    reason_codes: Iterable[str],
    effects: Iterable[str],
    targets: Iterable[dict[str, Any]],
    uncertainties: Iterable[str] = (),
    normalized_operation: dict[str, Any] | None = None,
    classifier_profile_id: str = "dc1-core-v1",
    native_artifact_id: str | None = None,
) -> dict[str, Any]:
    result = {
        "schema": RESULT_SCHEMA,
        "decision": decision,
        "reason_codes": _codes(reason_codes, "reason"),
        "effects": _effects(effects),
        "targets": _targets(targets),
        "uncertainties": _codes(uncertainties, "uncertainty"),
        "normalized_operation": normalized_operation,
        "operation_identity": operation_identity(normalized_operation) if normalized_operation is not None else None,
        "policy_provenance": {
            "native_artifact_id": native_artifact_id,
            "classifier_profile_id": classifier_profile_id,
        },
    }
    return validate_result(result)


def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(result, dict), "RESULT_OBJECT_REQUIRED")
    _require(result.get("schema") == RESULT_SCHEMA, "INVALID_RESULT_SCHEMA")
    decision = result.get("decision")
    _require(decision in DECISIONS, "INVALID_DECISION", decision)

    reasons = _codes(result.get("reason_codes", []), "reason")
    effects = _effects(result.get("effects", []))
    targets = _targets(result.get("targets", []))
    uncertainties = _codes(result.get("uncertainties", []), "uncertainty")

    normalized = result.get("normalized_operation")
    observed_identity = result.get("operation_identity")
    if normalized is not None:
        core = validate_operation_completeness(normalized)
        expected_identity = operation_identity(core)
        _require(observed_identity == expected_identity, "OPERATION_IDENTITY_MISMATCH")
        _require(effects == _effects(core["effects"]), "RESULT_EFFECTS_IDENTITY_MISMATCH")
        _require(
            [jcs_dumps(x) for x in targets] == [jcs_dumps(x) for x in _targets(core["targets"])],
            "RESULT_TARGETS_IDENTITY_MISMATCH",
        )
    else:
        _require(observed_identity is None, "IDENTITY_WITHOUT_OPERATION")

    if decision == "ALLOW":
        _require(not uncertainties, "ALLOW_WITH_UNCERTAINTY")
        _require(effects, "ALLOW_WITHOUT_EFFECTS")
        _require(not UNKNOWN_EFFECTS.intersection(effects), "ALLOW_WITH_UNKNOWN_EFFECT")
        _require(not any(t["kind"] in UNKNOWN_TARGET_KINDS for t in targets), "ALLOW_WITH_UNKNOWN_TARGET")
        _require(normalized is not None, "ALLOW_WITHOUT_OPERATION_IDENTITY")
        _require(isinstance(observed_identity, str) and IDENTITY_RE.fullmatch(observed_identity), "ALLOW_WITH_INVALID_IDENTITY")

    result["reason_codes"] = reasons
    result["effects"] = effects
    result["targets"] = targets
    result["uncertainties"] = uncertainties
    return result


def allow_result(operation: dict[str, Any], *, reason_codes: Iterable[str], classifier_profile_id: str = "dc1-core-v1") -> dict[str, Any]:
    core = validate_operation_completeness(operation)
    return make_result(
        "ALLOW",
        reason_codes=reason_codes,
        effects=core["effects"],
        targets=core["targets"],
        normalized_operation=core,
        classifier_profile_id=classifier_profile_id,
    )


def ask_result(*, reason_codes: Iterable[str], effects: Iterable[str] = (), targets: Iterable[dict[str, Any]] = (), uncertainties: Iterable[str]) -> dict[str, Any]:
    return make_result(
        "ASK_USER",
        reason_codes=reason_codes,
        effects=effects,
        targets=targets,
        uncertainties=uncertainties,
    )


def deny_result(*, reason_codes: Iterable[str], effects: Iterable[str] = (), targets: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    return make_result(
        "DENY",
        reason_codes=reason_codes,
        effects=effects,
        targets=targets,
    )


def combine_native_classifier(native_decision: str, classifier_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Enforce that native ALLOW/DENY are terminal and classifier handles only ASK."""
    _require(native_decision in NATIVE_DECISIONS, "INVALID_NATIVE_DECISION")
    if native_decision == "deny":
        return {"decision": "DENY", "source": "native"}
    if native_decision == "allow":
        return {"decision": "ALLOW", "source": "native"}
    if classifier_result is None:
        return {"decision": "ASK_USER", "source": "native_ask_no_classifier"}
    validated = validate_result(classifier_result)
    return {"decision": validated["decision"], "source": "classifier", "classifier_result": validated}


def _merge_child_facts(children: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]], list[str], list[str]]:
    effects = _effects(effect for child in children for effect in child["effects"])
    targets = _targets(target for child in children for target in child["targets"])
    reasons = _codes((code for child in children for code in child["reason_codes"]), "reason")
    uncertainties = _codes((code for child in children for code in child["uncertainties"]), "uncertainty")
    return effects, targets, reasons, uncertainties


def compose_results(
    children: Iterable[dict[str, Any]],
    *,
    parent_operation: dict[str, Any] | None = None,
    reason_code: str = "composition",
) -> dict[str, Any]:
    validated = [validate_result(child) for child in children]
    _require(validated, "COMPOSITION_REQUIRES_CHILDREN")
    effects, targets, reasons, uncertainties = _merge_child_facts(validated)
    reasons = _codes([*reasons, reason_code], "reason")

    if any(child["decision"] == "DENY" for child in validated):
        return deny_result(reason_codes=[*reasons, "composition.child_deny"], effects=effects, targets=targets)

    if any(child["decision"] == "ASK_USER" for child in validated):
        return ask_result(
            reason_codes=[*reasons, "composition.child_ask"],
            effects=effects,
            targets=targets,
            uncertainties=[*uncertainties, "composition.child_uncertainty"],
        )

    # All children are valid ALLOW results. A parent identity is still required.
    if parent_operation is None:
        return ask_result(
            reason_codes=[*reasons, "composition.parent_identity_required"],
            effects=effects,
            targets=targets,
            uncertainties=["identity.parent_missing"],
        )

    try:
        parent_core = validate_operation_completeness(parent_operation)
    except ClassifierError:
        return ask_result(
            reason_codes=[*reasons, "composition.parent_invalid"],
            effects=effects,
            targets=targets,
            uncertainties=["identity.parent_invalid"],
        )

    parent_effects = set(parent_core["effects"])
    child_effects = set(effects)
    if not child_effects.issubset(parent_effects):
        return ask_result(
            reason_codes=[*reasons, "composition.parent_effects_incomplete"],
            effects=_effects(parent_core["effects"]),
            targets=_targets(parent_core["targets"]),
            uncertainties=["composition.parent_effects_incomplete"],
        )

    parent_target_keys = {jcs_dumps(t) for t in _targets(parent_core["targets"])}
    child_target_keys = {jcs_dumps(t) for t in targets}
    if not child_target_keys.issubset(parent_target_keys):
        return ask_result(
            reason_codes=[*reasons, "composition.parent_targets_incomplete"],
            effects=_effects(parent_core["effects"]),
            targets=_targets(parent_core["targets"]),
            uncertainties=["composition.parent_targets_incomplete"],
        )

    if UNKNOWN_EFFECTS.intersection(parent_effects) or any(t["kind"] in UNKNOWN_TARGET_KINDS for t in parent_core["targets"]):
        return ask_result(
            reason_codes=[*reasons, "composition.parent_unknown"],
            effects=_effects(parent_core["effects"]),
            targets=_targets(parent_core["targets"]),
            uncertainties=["composition.parent_unknown"],
        )

    return allow_result(parent_core, reason_codes=[*reasons, "composition.all_children_allow"])

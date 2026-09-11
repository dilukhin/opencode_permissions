#!/usr/bin/env python3
"""Transitional YC runtime enforcement adapter.

This module is deliberately executor-agnostic. It never resolves PATH and never
spawns YC itself. A setup-owned runtime must supply a trusted downstream
executable identity and an executor that executes exactly that path.
"""
from __future__ import annotations

import copy
from typing import Any, Callable

from classifier_yc import analyze_yc

DECISION_SCHEMA = "yc-transitional-runtime-decision/v1"
FORBIDDEN_CALLER_KEYS = {
    "approved",
    "approval",
    "authorized",
    "authorization",
    "policy_allow",
    "skip_guard",
    "bypass",
}


class YcRuntimeContractError(RuntimeError):
    def __init__(self, code: str, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise YcRuntimeContractError(code, detail)


def _trusted_target(value: Any) -> dict[str, str]:
    _require(isinstance(value, dict), "TRUSTED_TARGET_REQUIRED")
    _require(value.get("invoked") == "yc", "TRUSTED_TARGET_INVOKED_MISMATCH")
    for field in ("resolved_path", "object_identity"):
        _require(isinstance(value.get(field), str) and value[field], f"TRUSTED_TARGET_{field.upper()}_REQUIRED")
    return {
        "invoked": "yc",
        "resolved_path": value["resolved_path"],
        "object_identity": value["object_identity"],
    }


def _reject_caller_approval(caller_context: Any) -> None:
    if caller_context is None:
        return
    _require(isinstance(caller_context, dict), "CALLER_CONTEXT_INVALID")
    forbidden = sorted(FORBIDDEN_CALLER_KEYS.intersection(caller_context))
    _require(not forbidden, "CALLER_APPROVAL_NOT_TRUSTED", forbidden)


def _verify_fact_target(fact: Any, trusted: dict[str, str]) -> None:
    _require(isinstance(fact, dict), "FACT_REQUIRED")
    executable = fact.get("executable")
    _require(isinstance(executable, dict), "FACT_EXECUTABLE_REQUIRED")
    observed = {
        "invoked": executable.get("invoked"),
        "resolved_path": executable.get("resolved_path"),
        "object_identity": executable.get("object_identity"),
    }
    _require(observed == trusted, "DOWNSTREAM_EXECUTABLE_IDENTITY_MISMATCH", observed)


def evaluate(
    fact: dict[str, Any],
    *,
    trusted_execution_target: dict[str, Any],
    caller_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate an exact fact without executing anything."""
    _reject_caller_approval(caller_context)
    trusted = _trusted_target(trusted_execution_target)
    _verify_fact_target(fact, trusted)

    classified = analyze_yc(fact)
    decision = classified["decision"]
    effects = list(classified.get("effects") or [])
    state_change = "cloud_state_change" in effects
    execute = decision == "ALLOW"

    return {
        "schema": DECISION_SCHEMA,
        "decision": decision,
        "execute": execute,
        "operation_identity": classified.get("operation_identity"),
        "reason_codes": list(classified.get("reason_codes") or []),
        "effects": effects,
        "targets": copy.deepcopy(classified.get("targets") or []),
        "trusted_execution_target": copy.deepcopy(trusted),
        "transitional_state_change_without_user_prompt": bool(execute and state_change),
        "classifier_result": classified,
    }


def dispatch(
    fact: dict[str, Any],
    *,
    trusted_execution_target: dict[str, Any],
    executor: Callable[[str, list[str]], Any],
    caller_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate and, only for canonical ALLOW, call the injected exact-path executor."""
    _require(callable(executor), "EXECUTOR_REQUIRED")
    outcome = evaluate(
        fact,
        trusted_execution_target=trusted_execution_target,
        caller_context=caller_context,
    )
    if not outcome["execute"]:
        outcome["execution_result"] = None
        return outcome

    argv = fact.get("argv")
    _require(isinstance(argv, list) and argv and argv[0] == "yc", "FACT_ARGV_INVALID")
    path = outcome["trusted_execution_target"]["resolved_path"]
    outcome["execution_result"] = executor(path, list(argv[1:]))
    return outcome

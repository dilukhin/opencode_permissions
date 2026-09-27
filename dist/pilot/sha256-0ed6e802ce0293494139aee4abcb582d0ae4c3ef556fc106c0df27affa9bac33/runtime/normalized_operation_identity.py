#!/usr/bin/env python3
"""Restricted JCS-compatible NormalizedOperation identity implementation.

The identity schema deliberately uses an I-JSON subset: strings, booleans, null,
safe integers, arrays, and objects. Floating point values are rejected. Semantic
set normalization is explicit and limited to fields declared as sets by the
NormalizedOperation v1 contract.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

DOMAIN = b"opencode_permissions.normalized_operation.v1\n"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
SUPPORTED_SCHEMA = "normalized-operation/v1"
SUPPORTED_CANONICALIZATION = "op-jcs-v1"

REQUIRED_TOP_LEVEL = (
    "schema",
    "canonicalization",
    "platform",
    "channel",
    "operation_kind",
    "execution",
    "targets",
    "effects",
    "context_dependencies",
)
OPTIONAL_IDENTITY_TOP_LEVEL = {"remote"}
EXCLUDED_TOP_LEVEL = {
    "purpose",
    "description",
    "display",
    "operation_id",
    "correlation_id",
    "session_id",
    "message_id",
    "call_id",
    "policy_artifact_id",
    "rule_id",
    "created_at",
    "reason",
}


class IdentityError(ValueError):
    def __init__(self, code: str, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise IdentityError(code, detail)


def _validate_unicode(value: str) -> str:
    _require(isinstance(value, str), "STRING_REQUIRED")
    for char in value:
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise IdentityError("INVALID_UNICODE_SURROGATE")
    return value


def _utf16_sort_key(value: str) -> bytes:
    return _validate_unicode(value).encode("utf-16-be")


def _jcs_string(value: str) -> str:
    _validate_unicode(value)
    out = ['"']
    short_escapes = {
        0x08: "\\b",
        0x09: "\\t",
        0x0A: "\\n",
        0x0C: "\\f",
        0x0D: "\\r",
    }
    for char in value:
        codepoint = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif codepoint in short_escapes:
            out.append(short_escapes[codepoint])
        elif codepoint < 0x20:
            out.append(f"\\u{codepoint:04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def jcs_dumps(value: Any) -> str:
    """Serialize the identity-schema JSON subset using RFC 8785 ordering rules."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        _require(
            abs(value) <= MAX_SAFE_INTEGER,
            "INTEGER_OUTSIDE_IJSON_SAFE_RANGE",
            value,
        )
        return str(value)
    if isinstance(value, float):
        raise IdentityError("FLOAT_NOT_ALLOWED")
    if isinstance(value, str):
        return _jcs_string(value)
    if isinstance(value, list):
        return "[" + ",".join(jcs_dumps(item) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            _require(isinstance(key, str), "OBJECT_KEY_NOT_STRING")
            _validate_unicode(key)
        keys = sorted(value.keys(), key=_utf16_sort_key)
        return "{" + ",".join(
            _jcs_string(key) + ":" + jcs_dumps(value[key]) for key in keys
        ) + "}"
    raise IdentityError("UNSUPPORTED_JSON_TYPE", type(value).__name__)


def _reject_float(raw: str) -> Any:
    raise IdentityError("FLOAT_NOT_ALLOWED", raw)


def _reject_constant(raw: str) -> Any:
    raise IdentityError("NON_FINITE_NUMBER_NOT_ALLOWED", raw)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IdentityError("DUPLICATE_OBJECT_KEY", key)
        result[key] = value
    return result


def strict_loads(payload: str) -> Any:
    return json.loads(
        payload,
        object_pairs_hook=_strict_object_pairs,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )


def load_json_strict(path: str | Path) -> Any:
    return strict_loads(Path(path).read_text(encoding="utf-8"))


def _semantic_set(items: list[Any]) -> list[Any]:
    canonical_to_item: dict[str, Any] = {}
    for item in items:
        key = jcs_dumps(item)
        canonical_to_item[key] = item
    return [canonical_to_item[key] for key in sorted(canonical_to_item)]


def extract_identity_core(operation: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(operation, dict), "OPERATION_OBJECT_REQUIRED")

    allowed = set(REQUIRED_TOP_LEVEL) | OPTIONAL_IDENTITY_TOP_LEVEL | EXCLUDED_TOP_LEVEL
    unknown = sorted(set(operation) - allowed)
    _require(not unknown, "UNKNOWN_TOP_LEVEL_FIELD", unknown)

    missing = [name for name in REQUIRED_TOP_LEVEL if name not in operation]
    _require(not missing, "MISSING_REQUIRED_FIELD", missing)

    _require(operation["schema"] == SUPPORTED_SCHEMA, "UNSUPPORTED_OPERATION_SCHEMA")
    _require(
        operation["canonicalization"] == SUPPORTED_CANONICALIZATION,
        "UNSUPPORTED_CANONICALIZATION",
    )
    _require(
        operation["platform"] in {"windows", "linux", "darwin", "other"},
        "INVALID_PLATFORM",
        operation["platform"],
    )
    _require(
        operation["channel"] in {"local", "remote", "transfer", "other"},
        "INVALID_CHANNEL",
        operation["channel"],
    )
    _require(
        isinstance(operation["operation_kind"], str) and operation["operation_kind"],
        "INVALID_OPERATION_KIND",
    )

    execution = operation["execution"]
    _require(isinstance(execution, dict), "INVALID_EXECUTION")
    _require(
        isinstance(execution.get("kind"), str) and execution["kind"],
        "INVALID_EXECUTION_KIND",
    )

    targets = operation["targets"]
    effects = operation["effects"]
    dependencies = operation["context_dependencies"]
    _require(isinstance(targets, list), "INVALID_TARGETS")
    _require(isinstance(effects, list), "INVALID_EFFECTS")
    _require(isinstance(dependencies, list), "INVALID_CONTEXT_DEPENDENCIES")

    for target in targets:
        _require(isinstance(target, dict), "INVALID_TARGET")
        _require(
            isinstance(target.get("role"), str) and target["role"],
            "TARGET_ROLE_REQUIRED",
        )
        _require(
            isinstance(target.get("kind"), str) and target["kind"],
            "TARGET_KIND_REQUIRED",
        )
        _require(isinstance(target.get("identity"), dict), "TARGET_IDENTITY_REQUIRED")

    for effect in effects:
        _require(isinstance(effect, str) and effect, "INVALID_EFFECT", effect)

    for dependency in dependencies:
        _require(isinstance(dependency, dict), "INVALID_CONTEXT_DEPENDENCY")
        _require(
            isinstance(dependency.get("kind"), str) and dependency["kind"],
            "CONTEXT_DEPENDENCY_KIND_REQUIRED",
        )
        if dependency.get("sensitive") is True or dependency.get("value_kind") == "secret":
            raise IdentityError("SENSITIVE_CONTEXT_DEPENDENCY_FORBIDDEN")

    core = {name: copy.deepcopy(operation[name]) for name in REQUIRED_TOP_LEVEL}
    if "remote" in operation:
        _require(isinstance(operation["remote"], dict), "INVALID_REMOTE")
        core["remote"] = copy.deepcopy(operation["remote"])

    # Only fields declared as semantic sets are normalized as sets.
    core["effects"] = sorted(set(core["effects"]), key=_utf16_sort_key)
    core["targets"] = _semantic_set(core["targets"])
    core["context_dependencies"] = _semantic_set(core["context_dependencies"])

    # Validate the whole resulting identity tree against the restricted JSON domain.
    jcs_dumps(core)
    return core


def canonical_identity_bytes(operation: dict[str, Any]) -> bytes:
    return jcs_dumps(extract_identity_core(operation)).encode("utf-8")


def operation_identity(operation: dict[str, Any]) -> str:
    digest = hashlib.sha256(DOMAIN + canonical_identity_bytes(operation)).hexdigest()
    return "sha256:" + digest


def identity_relation(left: dict[str, Any], right: dict[str, Any]) -> str:
    _require(isinstance(left, dict) and isinstance(right, dict), "OPERATION_OBJECT_REQUIRED")
    if (
        left.get("schema") != right.get("schema")
        or left.get("canonicalization") != right.get("canonicalization")
    ):
        return "NON_COMPARABLE"
    return "SAME" if operation_identity(left) == operation_identity(right) else "DIFFERENT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation_json")
    parser.add_argument("--show-core", action="store_true")
    args = parser.parse_args()

    operation = load_json_strict(args.operation_json)
    if args.show_core:
        print(jcs_dumps(extract_identity_core(operation)))
    print(operation_identity(operation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

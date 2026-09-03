#!/usr/bin/env python3
"""Deterministic OpenCode V1 native-permission renderer.

This module does not parse commands or classify effects. It only validates and
renders an already-approved ordered logical ruleset into OpenCode V1 config.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

CANONICAL_FORMAT = "native-policy/v1"
RULE_TUPLE = ["id", "permission", "pattern", "action"]
ACTIONS = {"ask", "allow", "deny"}


class RenderError(RuntimeError):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition, code, detail=None):
    if not condition:
        raise RenderError(code, detail)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def promote_candidate(candidate):
    _require(candidate.get("schema") == 1, "UNSUPPORTED_POLICY_SCHEMA")
    _require(candidate.get("rule_tuple") == RULE_TUPLE, "UNSUPPORTED_RULE_TUPLE")
    return {
        "schema": 1,
        "format": CANONICAL_FORMAT,
        "target": candidate["target"],
        "rule_tuple": RULE_TUPLE,
        "rules": candidate["rules"],
    }


def validate_canonical(policy):
    _require(policy.get("schema") == 1, "UNSUPPORTED_POLICY_SCHEMA")
    _require(policy.get("format") == CANONICAL_FORMAT, "UNSUPPORTED_POLICY_FORMAT")
    _require(policy.get("rule_tuple") == RULE_TUPLE, "UNSUPPORTED_RULE_TUPLE")
    _require(isinstance(policy.get("rules"), list) and policy["rules"], "EMPTY_RULESET")

    ids = set()
    permission_patterns = set()
    saw_specific_permission = False

    for index, row in enumerate(policy["rules"]):
        _require(isinstance(row, list) and len(row) == 4, "INVALID_RULE_ROW", index)
        rule_id, permission, pattern, action = row
        _require(all(isinstance(v, str) and v for v in row), "INVALID_RULE_VALUE", index)
        _require(action in ACTIONS, "INVALID_RULE_ACTION", rule_id)
        _require(rule_id not in ids, "DUPLICATE_RULE_ID", rule_id)
        ids.add(rule_id)

        pair = (permission, pattern)
        _require(pair not in permission_patterns, "DUPLICATE_PERMISSION_PATTERN", pair)
        permission_patterns.add(pair)

        if permission == "*":
            _require(
                not saw_specific_permission,
                "WILDCARD_PERMISSION_AFTER_SPECIFIC",
                rule_id,
            )
        else:
            saw_specific_permission = True
            _require(
                "*" not in permission and "?" not in permission,
                "UNREPRESENTABLE_PERMISSION_PATTERN",
                permission,
            )

    first = policy["rules"][0]
    _require(
        first[1:] == ["*", "*", "ask"],
        "FIRST_RULE_MUST_BE_FAIL_CLOSED_FALLBACK",
        first[0],
    )
    return policy


def canonical_bytes(policy):
    validate_canonical(policy)
    return (json.dumps(policy, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render_config(policy):
    validate_canonical(policy)
    permission = {}
    for _, permission_name, pattern, action in policy["rules"]:
        bucket = permission.setdefault(permission_name, {})
        bucket[pattern] = action
    return {"permission": permission}


def render_bytes(policy):
    payload = render_config(policy)
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def flatten_rendered(config):
    out = []
    seq = 0
    for permission, value in config["permission"].items():
        _require(isinstance(value, dict), "RENDERED_PERMISSION_NOT_OBJECT", permission)
        for pattern, action in value.items():
            seq += 1
            out.append(
                {
                    "id": f"rendered.{seq}",
                    "permission": permission,
                    "pattern": pattern,
                    "action": action,
                }
            )
    return out


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def emit_promotion_evidence(candidate_path):
    candidate = load_json(candidate_path)
    canonical = promote_candidate(candidate)
    source = canonical_bytes(canonical)
    output = render_bytes(canonical)
    print("PROMOTION_SOURCE_SHA256=" + sha256_bytes(source))
    print("PROMOTION_OUTPUT_SHA256=" + sha256_bytes(output))
    print("PROMOTION_CANONICAL_B64=" + base64.b64encode(source).decode("ascii"))
    print("PROMOTION_OUTPUT_B64=" + base64.b64encode(output).decode("ascii"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("--output")
    p.add_argument("--promote-candidate", action="store_true")
    p.add_argument("--promotion-evidence", action="store_true")
    a = p.parse_args()

    if a.promotion_evidence:
        emit_promotion_evidence(a.source)
        return 0

    source = load_json(a.source)
    policy = promote_candidate(source) if a.promote_candidate else source
    output = render_bytes(policy)
    if a.output:
        Path(a.output).write_bytes(output)
    else:
        sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())

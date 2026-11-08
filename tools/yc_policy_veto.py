"""Shared deterministic YC hard veto; never issues approval or executes commands."""
from typing import Any

def _option_name(token: str) -> str | None:
    if not token.startswith("--"):
        return None
    return token.split("=", 1)[0]


def denial_reason(args: list[str], policy: dict[str, Any]) -> str | None:
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



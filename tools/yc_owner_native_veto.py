"""Protected owner's canonical veto, separate from untrusted OpenCode replies.

The native composition root must hold both verified source files for the entire
host lifetime. Bytes/hashes alone do not prove that root or file protection.
This module is not an approval issuer, shell parser, or live OpenCode observer.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess

from native_policy_matcher import evaluate_pattern
from render_native_policy import validate_canonical
from yc_policy_veto import denial_reason
from yc_snapshot_read import ReadError, exact_read_argv, require

DOMAIN = b"yc59.protected-native-veto.v1\n"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "YC_VETO_SOURCE_INVALID")
        result[key] = value
    return result


def _source(raw, expected):
    require(type(raw) is bytes and 0 < len(raw) <= 65536, "YC_VETO_SOURCE_INVALID")
    require(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
            "YC_VETO_SOURCE_INVALID")
    require(hashlib.sha256(raw).hexdigest() == expected, "YC_VETO_SOURCE_CHANGED")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        require(type(value) is dict, "YC_VETO_SOURCE_INVALID")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ReadError("YC_VETO_SOURCE_INVALID") from None


def _strings(value):
    return (type(value) is list and 0 < len(value) <= 512
            and all(type(x) is str and 0 < len(x) <= 1024
                    and all(32 <= ord(c) < 127 for c in x) for x in value))


class NativeVeto:
    def __init__(self, native_bytes, yc_bytes, *, native_sha256, yc_sha256):
        native = _source(native_bytes, native_sha256)
        yc = _source(yc_bytes, yc_sha256)
        try:
            validate_canonical(native)
            require(type(native.get("target")) is dict
                    and native["target"].get("permission_semantics") == "v1_last_match_wins",
                    "YC_VETO_SEMANTICS_UNSUPPORTED")
            require(len(native["rules"]) <= 512 and all(_strings(row) for row in native["rules"]),
                    "YC_VETO_SOURCE_INVALID")
            require(yc.get("schema") == "yc-policy/v1" and yc.get("provider") == "yandex-cloud",
                    "YC_VETO_SOURCE_INVALID")
            deny = yc["deny"]
            require(type(deny) is dict and set(deny) == {
                "guard_denied_sequences", "sequences", "sensitive_config_keys", "sensitive_flags"},
                "YC_VETO_SOURCE_INVALID")
            for key in ("guard_denied_sequences", "sequences"):
                require(type(deny[key]) is list and 0 < len(deny[key]) <= 512
                        and all(_strings(row) for row in deny[key]), "YC_VETO_SOURCE_INVALID")
            for key in ("sensitive_config_keys", "sensitive_flags"):
                require(_strings(deny[key]), "YC_VETO_SOURCE_INVALID")
        except ReadError:
            raise
        except Exception:
            raise ReadError("YC_VETO_SOURCE_INVALID") from None
        # Copies are private and immutable at the interface. No caller can supply
        # a decision, argv, rules override, or policy revision to check().
        self._rules = tuple({"id": row[0], "permission": row[1], "pattern": row[2], "action": row[3]}
                            for row in native["rules"])
        self._yc = yc
        self.revision = hashlib.sha256(DOMAIN + native_sha256.encode("ascii") + b"\n"
                                       + yc_sha256.encode("ascii") + b"\n").hexdigest()

    def check(self, ctx):
        require(ctx.platform == "windows", "YC_VETO_PLATFORM_UNSUPPORTED")
        require(ctx.policy_revision == self.revision, "YC_VETO_REVISION_CHANGED")
        steps = exact_read_argv(ctx)
        any_ask = False
        for argv in steps:
            # Evaluate both the stable logical command and actual Windows path
            # spelling. Neither string comes from a pipe client or shell parser.
            patterns = (" ".join(["yc", *argv[1:]]), subprocess.list2cmdline(argv))
            for pattern in patterns:
                result = evaluate_pattern("bash", pattern, self._rules, "win32")
                if result["action"] == "deny":
                    return "deny"
                any_ask |= result["action"] == "ask"
            if denial_reason(argv[1:], self._yc) is not None:
                return "deny"
        # Even allow does not dispense with the existing Ledger/human once.
        return "ask" if any_ask else "allow"

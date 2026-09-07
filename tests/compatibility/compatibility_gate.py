#!/usr/bin/env python3
"""Exact-version selector and rolling fingerprint-family compatibility gate."""
import hashlib
import json
from pathlib import Path

FAMILY_DOMAIN = b"opencode_permissions.compatibility_family.v1\n"


class CompatibilityError(RuntimeError):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_profile(registry_path, version, require_deployable=False, platform=None):
    registry_path = Path(registry_path)
    registry = load_json(registry_path)
    rel = registry["profiles"].get(version)
    if rel is None:
        raise CompatibilityError(registry["unknown_version_result"], {"version": version})
    profile = load_json(registry_path.parent / rel)
    if profile["opencode_version"] != version:
        raise CompatibilityError(
            "PROFILE_VERSION_MISMATCH",
            {"requested": version, "profile": profile["opencode_version"]},
        )
    if require_deployable:
        if not profile.get("deployable"):
            raise CompatibilityError(
                registry["not_deployable_result"],
                {"version": version, "platform": platform},
            )
        if platform is None:
            raise CompatibilityError("DEPLOYABLE_PLATFORM_REQUIRED", {"version": version})
        if platform not in profile.get("deployable_platforms", []):
            raise CompatibilityError(
                "PROFILE_NOT_DEPLOYABLE_FOR_PLATFORM",
                {"version": version, "platform": platform},
            )
    return profile


def current_target_profile(registry_path):
    registry = load_json(registry_path)
    version = registry.get("current_target")
    if not isinstance(version, str) or not version:
        raise CompatibilityError("CURRENT_TARGET_MISSING")
    return select_profile(registry_path, version)


def _fingerprint_rows(profile, keys):
    fingerprints = profile.get("critical_fingerprints")
    if not isinstance(fingerprints, dict):
        raise CompatibilityError("CRITICAL_FINGERPRINTS_MISSING")
    rows = []
    missing = []
    invalid = []
    for key in keys:
        item = fingerprints.get(key)
        if item is None:
            missing.append(key)
            continue
        path = item.get("path") if isinstance(item, dict) else None
        blob = item.get("blob") if isinstance(item, dict) else None
        if not isinstance(path, str) or not path or not isinstance(blob, str) or not blob:
            invalid.append(key)
            continue
        rows.append({"key": key, "path": path, "blob": blob})
    if missing or invalid:
        raise CompatibilityError(
            "CRITICAL_FINGERPRINT_SET_INCOMPLETE",
            {"missing": missing, "invalid": invalid},
        )
    return sorted(rows, key=lambda row: row["key"])


def compatibility_family_id(profile, keys):
    rows = _fingerprint_rows(profile, keys)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(FAMILY_DOMAIN + payload).hexdigest()


def compare_fingerprint_family(baseline_profile, candidate_profile, keys):
    try:
        before_rows = _fingerprint_rows(baseline_profile, keys)
        after_rows = _fingerprint_rows(candidate_profile, keys)
    except CompatibilityError as exc:
        return {
            "result": "TARGETED_REAUDIT_REQUIRED",
            "changed_fingerprints": [],
            "missing_or_invalid": exc.detail,
            "family_id": None,
        }

    before = {row["key"]: (row["path"], row["blob"]) for row in before_rows}
    after = {row["key"]: (row["path"], row["blob"]) for row in after_rows}
    changed = [key for key in keys if before[key] != after[key]]
    if changed:
        return {
            "result": "TARGETED_REAUDIT_REQUIRED",
            "changed_fingerprints": changed,
            "missing_or_invalid": None,
            "family_id": None,
        }
    return {
        "result": "SOURCE_EQUIVALENT",
        "changed_fingerprints": [],
        "missing_or_invalid": None,
        "family_id": compatibility_family_id(candidate_profile, keys),
    }


def compare_fast_path(baseline_profile, candidate_profile, keys):
    """Backward-compatible name for older Gate B tests/docs."""
    result = compare_fingerprint_family(baseline_profile, candidate_profile, keys)
    return {
        "result": (
            "SOURCE_EQUIVALENT_FAST_PATH_ELIGIBLE"
            if result["result"] == "SOURCE_EQUIVALENT"
            else "TARGETED_REAUDIT_REQUIRED"
        ),
        "changed_fingerprints": result["changed_fingerprints"],
    }

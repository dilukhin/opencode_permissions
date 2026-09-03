#!/usr/bin/env python3
"""Test-only exact-version/platform compatibility selector for Gate B."""
import json
from pathlib import Path


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


def compare_fast_path(baseline_profile, candidate_profile, keys):
    changed = []
    for key in keys:
        before = baseline_profile["critical_fingerprints"].get(key)
        after = candidate_profile["critical_fingerprints"].get(key)
        if before != after:
            changed.append(key)
    return {
        "result": (
            "SOURCE_EQUIVALENT_FAST_PATH_ELIGIBLE"
            if not changed
            else "TARGETED_REAUDIT_REQUIRED"
        ),
        "changed_fingerprints": changed,
    }

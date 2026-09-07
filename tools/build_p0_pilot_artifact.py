#!/usr/bin/env python3
"""Build/validate the content-bound Minimal Managed Pilot P0 runtime artifact."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

DOMAIN = b"opencode_permissions.pilot_artifact.v1\n"
ARTIFACT_FORMAT = "opencode-permissions-pilot-artifact/v1"
OWNER = "dilukhin/opencode_permissions"
PLATFORM = "linux"

BUNDLE_SOURCES = {
    "bridge.js": "runtime/p0/opencode-permissions.js",
    "runtime/opencode_p0_adapter.py": "tools/opencode_p0_adapter.py",
    "runtime/classifier_analyzers.py": "tools/classifier_analyzers.py",
    "runtime/classifier_core.py": "tools/classifier_core.py",
    "runtime/normalized_operation_identity.py": "tools/normalized_operation_identity.py",
}


class PilotArtifactError(RuntimeError):
    def __init__(self, code: str, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise PilotArtifactError(code, detail)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "JSON_OBJECT_REQUIRED", str(path))
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_identity_core(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_format": manifest["artifact_format"],
        "owner": manifest["owner"],
        "target": manifest["target"],
        "native_policy_artifact_id": manifest["native_policy_artifact_id"],
        "classifier_profile": manifest["classifier_profile"],
        "files": manifest["files"],
        "constraints": manifest["constraints"],
    }


def compute_artifact_id(manifest: dict[str, Any]) -> str:
    return "sha256:" + _sha256(DOMAIN + _canonical(artifact_identity_core(manifest)))


def _artifact_segment(artifact_id: str) -> str:
    _require(artifact_id.startswith("sha256:"), "INVALID_ARTIFACT_ID")
    return "sha256-" + artifact_id.split(":", 1)[1]


def _resolve_current_target(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    compatibility_root = root / "tests" / "compatibility"
    registry = _load_json(compatibility_root / "registry.json")
    _require(registry.get("selection") == "exact_version_only", "REGISTRY_NOT_EXACT_ONLY")
    _require(registry.get("nearest_version_fallback") is False, "REGISTRY_NEAREST_FALLBACK_ENABLED")

    version = registry.get("current_target")
    _require(isinstance(version, str) and version, "CURRENT_TARGET_MISSING")
    profile_rel = (registry.get("profiles") or {}).get(version)
    _require(isinstance(profile_rel, str), "CURRENT_PROFILE_MISSING", version)
    profile = _load_json(compatibility_root / profile_rel)

    _require(profile.get("opencode_version") == version, "PROFILE_VERSION_MISMATCH")
    _require(profile.get("deployable") is True, "PROFILE_NOT_DEPLOYABLE")
    _require(PLATFORM in profile.get("deployable_platforms", []), "PROFILE_NOT_DEPLOYABLE_FOR_LINUX")
    _require((profile.get("platform_status") or {}).get(PLATFORM) == "RUNTIME_REVALIDATED", "PROFILE_NOT_RUNTIME_REVALIDATED")

    native_id = (profile.get("policy_artifacts") or {}).get(PLATFORM)
    _require(isinstance(native_id, str) and native_id.startswith("sha256:"), "NATIVE_ARTIFACT_MISSING")
    native_dir = root / "dist" / "opencode" / _artifact_segment(native_id)
    native_manifest = _load_json(native_dir / "manifest.json")
    _require(native_manifest.get("artifact_id") == native_id, "NATIVE_ARTIFACT_ID_MISMATCH")
    _require((native_manifest.get("target") or {}).get("exact_version") == version, "NATIVE_ARTIFACT_VERSION_MISMATCH")
    _require((native_manifest.get("target") or {}).get("platform") == PLATFORM, "NATIVE_ARTIFACT_PLATFORM_MISMATCH")
    _require(
        (native_manifest.get("target") or {}).get("compatibility_profile_id") == profile.get("profile_id"),
        "NATIVE_ARTIFACT_PROFILE_MISMATCH",
    )
    return registry, profile, native_manifest, native_dir


def _canonical_secret_rules(root: Path, source_profile: dict[str, Any]) -> list[dict[str, str]]:
    policy = _load_json(root / "policy" / "native" / "rules.v1.json")
    tuple_fields = policy.get("rule_tuple")
    _require(tuple_fields == ["id", "permission", "pattern", "action"], "NATIVE_RULE_TUPLE_UNEXPECTED")
    boundary = source_profile.get("secret_boundary") or {}
    permission = boundary.get("permission")
    prefix = boundary.get("rule_id_prefix")
    actions = set(boundary.get("actions") or [])
    _require(permission == "read" and isinstance(prefix, str) and prefix, "P0_SECRET_BOUNDARY_INVALID")
    _require(actions == {"ask", "deny"}, "P0_SECRET_ACTIONS_INVALID")

    resolved = []
    for row in policy.get("rules") or []:
        _require(isinstance(row, list) and len(row) == 4, "NATIVE_RULE_ROW_INVALID")
        rule_id, rule_permission, pattern, action = row
        if rule_permission == permission and isinstance(rule_id, str) and rule_id.startswith(prefix):
            _require(action in actions, "P0_SECRET_RULE_ACTION_UNEXPECTED", rule_id)
            resolved.append({"id": rule_id, "pattern": pattern, "action": action})
    _require(resolved, "P0_SECRET_RULES_EMPTY")
    return resolved


def build_runtime_profile(root: Path, compatibility: dict[str, Any], native_manifest: dict[str, Any]) -> dict[str, Any]:
    source = _load_json(root / "pilot" / "p0" / "profile.v1.json")
    _require(source.get("profile_format") == "opencode-permissions-p0-classifier-profile/v1", "P0_PROFILE_FORMAT_INVALID")
    _require(source.get("platform") == PLATFORM, "P0_PROFILE_PLATFORM_INVALID")
    _require(source.get("allow_families") == ["grep.single_nonsecret_workspace_file"], "P0_ALLOW_SURFACE_WIDENED")

    constraints = source.get("constraints") or {}
    for key in (
        "recursive_search",
        "pipelines",
        "compound_shell",
        "redirects",
        "find",
        "git",
        "build_test_static_check",
        "state_changing",
        "remote",
        "auditor",
        "workspace_trust",
    ):
        _require(constraints.get(key) is False, "P0_CONSTRAINT_WIDENED", key)
    _require(constraints.get("single_simple_command_only") is True, "P0_SIMPLE_COMMAND_REQUIRED")
    _require(constraints.get("exactly_one_existing_workspace_file") is True, "P0_SINGLE_FILE_REQUIRED")

    runtime = copy.deepcopy(source)
    runtime["target"] = {
        "opencode_version": compatibility["opencode_version"],
        "compatibility_profile_id": compatibility["profile_id"],
        "compatibility_family_id": compatibility["compatibility_family"]["family_id"],
        "native_policy_artifact_id": native_manifest["artifact_id"],
    }
    runtime["secret_boundary"]["resolved_rules"] = _canonical_secret_rules(root, source)
    return runtime


def build_plan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    _, compatibility, native_manifest, _ = _resolve_current_target(root)
    runtime_profile = build_runtime_profile(root, compatibility, native_manifest)
    runtime_profile_bytes = json.dumps(runtime_profile, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"

    payloads: dict[str, bytes] = {"profile.json": runtime_profile_bytes}
    for dest, source in BUNDLE_SOURCES.items():
        payloads[dest] = (root / source).read_bytes()

    files = [
        {"path": name, "sha256": _sha256(payloads[name]), "size": len(payloads[name])}
        for name in sorted(payloads)
    ]
    profile_record = next(item for item in files if item["path"] == "profile.json")

    manifest: dict[str, Any] = {
        "schema": 1,
        "artifact_format": ARTIFACT_FORMAT,
        "artifact_id": "",
        "status": "mp0_ready",
        "owner": OWNER,
        "target": {
            "product": "opencode",
            "exact_version": compatibility["opencode_version"],
            "platform": PLATFORM,
            "compatibility_profile_id": compatibility["profile_id"],
            "compatibility_family_id": compatibility["compatibility_family"]["family_id"],
        },
        "native_policy_artifact_id": native_manifest["artifact_id"],
        "classifier_profile": {
            "id": runtime_profile["classifier_profile_id"],
            "relative_path": "profile.json",
            "sha256": profile_record["sha256"],
        },
        "files": files,
        "constraints": {
            "exact_version_only": True,
            "requires_deployable_profile": True,
            "nearest_version_fallback": False,
            "setup_semantic_rewrite": False,
            "managed_global_plugin_required": True,
            "developer_checkout_dependency": False,
            "auditor_enabled": False,
            "workspace_trust_enabled": False,
            "state_changing_classifier_enabled": False,
            "classifier_error_result": "ASK_USER",
            "competing_effective_layer_result": "CONFLICT",
            "runtime_bundle_digest_check": True,
        },
        "artifact_path_segment": "",
    }
    artifact_id = compute_artifact_id(manifest)
    manifest["artifact_id"] = artifact_id
    manifest["artifact_path_segment"] = _artifact_segment(artifact_id)

    return {
        "artifact_id": artifact_id,
        "artifact_path": f"dist/pilot/{manifest['artifact_path_segment']}",
        "manifest": manifest,
        "runtime_profile": runtime_profile,
        "payloads": payloads,
    }


def validate_committed_artifact(root: Path) -> dict[str, Any]:
    plan = build_plan(root)
    artifact_dir = root / plan["artifact_path"]
    _require(artifact_dir.is_dir(), "P0_ARTIFACT_DIRECTORY_MISSING", str(artifact_dir))
    observed = _load_json(artifact_dir / "manifest.json")
    _require(observed == plan["manifest"], "P0_MANIFEST_MISMATCH")

    for item in observed["files"]:
        path = artifact_dir / item["path"]
        _require(path.is_file(), "P0_ARTIFACT_FILE_MISSING", item["path"])
        data = path.read_bytes()
        _require(len(data) == item["size"], "P0_ARTIFACT_FILE_SIZE_MISMATCH", item["path"])
        _require(_sha256(data) == item["sha256"], "P0_ARTIFACT_FILE_DIGEST_MISMATCH", item["path"])
        expected = plan["payloads"][item["path"]]
        _require(data == expected, "P0_ARTIFACT_FILE_CONTENT_MISMATCH", item["path"])

    return {
        "result": "MP0_ARTIFACT_VALID",
        "artifact_id": observed["artifact_id"],
        "artifact_path": plan["artifact_path"],
        "opencode_version": observed["target"]["exact_version"],
        "classifier_profile_id": observed["classifier_profile"]["id"],
    }


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": plan["artifact_id"],
        "artifact_path": plan["artifact_path"],
        "manifest": plan["manifest"],
        "runtime_profile": plan["runtime_profile"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    if args.check:
        print(json.dumps(validate_committed_artifact(root), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    else:
        print(json.dumps(_public_plan(build_plan(root)), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

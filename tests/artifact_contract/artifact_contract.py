#!/usr/bin/env python3
"""Validator for the Gate B canonical artifact contract."""
import hashlib
import json
from pathlib import Path

DOMAIN = b"opencode_permissions.artifact.v1\n"


class ArtifactContractError(RuntimeError):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def identity_core(manifest):
    return {
        "artifact_format": manifest["artifact_format"],
        "owner": manifest["owner"],
        "target": manifest["target"],
        "policy_source_sha256": manifest["policy_source"]["sha256"],
        "renderer": manifest["renderer"],
        "output_sha256": manifest["output"]["sha256"],
    }


def compute_artifact_id(manifest):
    payload = json.dumps(
        identity_core(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(DOMAIN + payload).hexdigest()


def artifact_path_segment(artifact_id):
    if not isinstance(artifact_id, str) or not artifact_id.startswith("sha256:"):
        raise ArtifactContractError("INVALID_ARTIFACT_ID")
    return "sha256-" + artifact_id.split(":", 1)[1]


def _require(condition, code, detail=None):
    if not condition:
        raise ArtifactContractError(code, detail)


def validate_contract(
    manifest,
    profile,
    installed_version,
    source_root,
    artifact_dir,
    installed_platform=None,
):
    _require(manifest.get("schema") == 1, "UNSUPPORTED_MANIFEST_SCHEMA")
    _require(
        manifest.get("artifact_format") == "opencode-permission-artifact/v1",
        "UNSUPPORTED_ARTIFACT_FORMAT",
    )
    _require(manifest.get("owner") == "dilukhin/opencode_permissions", "WRONG_SEMANTIC_OWNER")
    _require(manifest.get("status") == "deployable", "ARTIFACT_NOT_DEPLOYABLE")

    target = manifest["target"]
    _require(installed_platform is not None, "INSTALLED_PLATFORM_REQUIRED")
    _require(target.get("product") == "opencode", "WRONG_TARGET_PRODUCT")
    _require(target.get("exact_version") == installed_version, "INSTALLED_VERSION_MISMATCH")
    _require(target.get("platform") == installed_platform, "INSTALLED_PLATFORM_MISMATCH")
    _require(profile.get("opencode_version") == installed_version, "PROFILE_VERSION_MISMATCH")
    _require(
        target.get("compatibility_profile_id") == profile.get("profile_id"),
        "PROFILE_ID_MISMATCH",
    )
    _require(profile.get("deployable") is True, "PROFILE_NOT_DEPLOYABLE")
    _require(
        installed_platform in profile.get("deployable_platforms", []),
        "PROFILE_NOT_DEPLOYABLE_FOR_PLATFORM",
    )
    _require(
        profile.get("policy_artifacts", {}).get(installed_platform) == manifest.get("artifact_id"),
        "PROFILE_ARTIFACT_ID_MISMATCH",
    )

    expected_segment = artifact_path_segment(manifest.get("artifact_id"))
    _require(
        manifest.get("artifact_path_segment") == expected_segment,
        "ARTIFACT_PATH_SEGMENT_MISMATCH",
    )
    _require(Path(artifact_dir).name == expected_segment, "ARTIFACT_DIRECTORY_MISMATCH")

    constraints = manifest["constraints"]
    _require(constraints.get("exact_version_only") is True, "EXACT_VERSION_REQUIRED")
    _require(
        constraints.get("requires_deployable_profile") is True,
        "DEPLOYABLE_PROFILE_REQUIRED",
    )
    _require(
        constraints.get("nearest_version_fallback") is False,
        "NEAREST_VERSION_FALLBACK_FORBIDDEN",
    )
    _require(
        constraints.get("setup_semantic_rewrite") is False,
        "SETUP_SEMANTIC_REWRITE_FORBIDDEN",
    )
    _require(
        constraints.get("effective_readback_required") is True,
        "EFFECTIVE_READBACK_REQUIRED",
    )
    _require(
        constraints.get("competing_effective_layer_result") == "CONFLICT",
        "COMPETING_LAYER_MUST_CONFLICT",
    )

    source_rel = Path(manifest["policy_source"]["path"])
    _require(
        not source_rel.is_absolute() and ".." not in source_rel.parts,
        "INVALID_POLICY_SOURCE_PATH",
    )
    _require(source_rel.parts[:2] == ("policy", "native"), "NONCANONICAL_POLICY_SOURCE")
    output_rel = Path(manifest["output"]["relative_path"])
    _require(output_rel == Path("permission.jsonc"), "NONCANONICAL_OUTPUT_PATH")

    source = Path(source_root) / source_rel
    output = Path(artifact_dir) / output_rel
    _require(source.is_file(), "POLICY_SOURCE_MISSING")
    _require(output.is_file(), "ARTIFACT_OUTPUT_MISSING")
    _require(
        sha256_file(source) == manifest["policy_source"]["sha256"],
        "POLICY_SOURCE_DIGEST_MISMATCH",
    )
    _require(
        sha256_file(output) == manifest["output"]["sha256"],
        "ARTIFACT_OUTPUT_DIGEST_MISMATCH",
    )
    _require(compute_artifact_id(manifest) == manifest["artifact_id"], "ARTIFACT_ID_MISMATCH")

    return {
        "result": "VALID_DEPLOYABLE_ARTIFACT_CONTRACT",
        "artifact_id": manifest["artifact_id"],
        "artifact_path_segment": expected_segment,
        "exact_version": installed_version,
        "platform": installed_platform,
        "effective_readback_required": True,
    }

#!/usr/bin/env python3
"""Build/validate the content-bound transitional YC runtime artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DOMAIN = b"opencode_permissions.yc_transitional_artifact.v1\n"
ARTIFACT_FORMAT = "opencode-permissions-yc-transitional-artifact/v1"
OWNER = "dilukhin/opencode_permissions"

BUNDLE_SOURCES = {
    "policy/yc/yc_policy.v1.json": "policy/yc/yc_policy.v1.json",
    "runtime/yc_transitional_adapter.py": "runtime/yc_guard/yc_transitional_adapter.py",
    "runtime/classifier_yc.py": "tools/classifier_yc.py",
    "runtime/classifier_core.py": "tools/classifier_core.py",
    "runtime/normalized_operation_identity.py": "tools/normalized_operation_identity.py",
}


class YcArtifactError(RuntimeError):
    def __init__(self, code: str, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise YcArtifactError(code, detail)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_policy(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "YC_POLICY_OBJECT_REQUIRED")
    _require(value.get("schema") == "yc-policy/v1", "YC_POLICY_SCHEMA_UNSUPPORTED")
    _require(isinstance(value.get("version"), str) and value["version"], "YC_POLICY_VERSION_REQUIRED")
    _require(value.get("provider") == "yandex-cloud", "YC_POLICY_PROVIDER_UNEXPECTED")
    return value


def artifact_identity_core(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_format": manifest["artifact_format"],
        "owner": manifest["owner"],
        "target": manifest["target"],
        "policy": manifest["policy"],
        "files": manifest["files"],
        "constraints": manifest["constraints"],
        "transitional_auto_allow_mutations": manifest["transitional_auto_allow_mutations"],
    }


def compute_artifact_id(manifest: dict[str, Any]) -> str:
    return "sha256:" + _sha256(DOMAIN + _canonical(artifact_identity_core(manifest)))


def _segment(artifact_id: str) -> str:
    _require(artifact_id.startswith("sha256:"), "YC_ARTIFACT_ID_INVALID")
    return "sha256-" + artifact_id.split(":", 1)[1]


def build_plan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    policy = _load_policy(root / "policy" / "yc" / "yc_policy.v1.json")
    payloads = {dest: (root / source).read_bytes() for dest, source in BUNDLE_SOURCES.items()}
    files = [
        {"path": path, "sha256": _sha256(data), "size": len(data)}
        for path, data in sorted(payloads.items())
    ]
    policy_record = next(item for item in files if item["path"] == "policy/yc/yc_policy.v1.json")

    mutations = []
    for item in policy.get("allow_mutations") or []:
        _require(isinstance(item, dict), "YC_POLICY_MUTATION_INVALID")
        _require(isinstance(item.get("resource_id"), str) and item["resource_id"], "YC_POLICY_MUTATION_ID_REQUIRED")
        _require(isinstance(item.get("argv"), list) and all(isinstance(x, str) for x in item["argv"]), "YC_POLICY_MUTATION_ARGV_INVALID")
        mutations.append({
            "service": item.get("service"),
            "resource": item.get("resource"),
            "action": item.get("action"),
            "resource_id": item["resource_id"],
            "argv": list(item["argv"]),
        })

    manifest: dict[str, Any] = {
        "schema": 1,
        "artifact_format": ARTIFACT_FORMAT,
        "artifact_id": "",
        "status": "transitional_ready",
        "owner": OWNER,
        "target": {
            "provider": "yandex-cloud",
            "platform": "windows",
            "mode": "transitional",
        },
        "policy": {
            "schema": policy["schema"],
            "version": policy["version"],
            "relative_path": "policy/yc/yc_policy.v1.json",
            "sha256": policy_record["sha256"],
        },
        "files": files,
        "constraints": {
            "canonical_policy_only": True,
            "setup_semantic_rewrite": False,
            "developer_checkout_dependency": False,
            "hard_deny_terminal": True,
            "unknown_or_opaque_not_allow": True,
            "runtime_path_resolution": False,
            "downstream_executable_identity_required": True,
            "caller_approval_flags_trusted": False,
            "real_executor_packaged": False,
            "transitional_exact_mutation_auto_allow": True,
            "full_authorization_binding_complete": False,
        },
        "transitional_auto_allow_mutations": mutations,
        "artifact_path_segment": "",
    }
    artifact_id = compute_artifact_id(manifest)
    manifest["artifact_id"] = artifact_id
    manifest["artifact_path_segment"] = _segment(artifact_id)
    return {
        "artifact_id": artifact_id,
        "artifact_path": f"dist/yc-runtime/{manifest['artifact_path_segment']}",
        "manifest": manifest,
        "payloads": payloads,
    }


def _write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        _require(path.is_file(), "YC_ARTIFACT_OUTPUT_NOT_FILE", str(path))
        _require(path.read_bytes() == data, "YC_ARTIFACT_OUTPUT_CONFLICT", str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def materialize(root: Path, output_root: Path | None = None) -> dict[str, Any]:
    plan = build_plan(root)
    base = (output_root or root / "dist" / "yc-runtime").resolve()
    artifact_dir = base / plan["manifest"]["artifact_path_segment"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for rel, data in plan["payloads"].items():
        _write_exact(artifact_dir / rel, data)
    manifest_bytes = json.dumps(plan["manifest"], indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    _write_exact(artifact_dir / "manifest.json", manifest_bytes)
    validate_artifact(root, artifact_dir)
    return {
        "result": "YC_TRANSITIONAL_ARTIFACT_WRITTEN",
        "artifact_id": plan["artifact_id"],
        "artifact_dir": str(artifact_dir),
    }


def validate_artifact(root: Path, artifact_dir: Path) -> dict[str, Any]:
    plan = build_plan(root)
    manifest_path = artifact_dir / "manifest.json"
    _require(manifest_path.is_file(), "YC_ARTIFACT_MANIFEST_MISSING")
    observed = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(observed == plan["manifest"], "YC_ARTIFACT_MANIFEST_MISMATCH")

    for item in observed["files"]:
        path = artifact_dir / item["path"]
        _require(path.is_file(), "YC_ARTIFACT_FILE_MISSING", item["path"])
        data = path.read_bytes()
        _require(len(data) == item["size"], "YC_ARTIFACT_FILE_SIZE_MISMATCH", item["path"])
        _require(_sha256(data) == item["sha256"], "YC_ARTIFACT_FILE_DIGEST_MISMATCH", item["path"])
        _require(data == plan["payloads"][item["path"]], "YC_ARTIFACT_FILE_CONTENT_MISMATCH", item["path"])

    return {
        "result": "YC_TRANSITIONAL_ARTIFACT_VALID",
        "artifact_id": observed["artifact_id"],
        "artifact_dir": str(artifact_dir),
    }


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": plan["artifact_id"],
        "artifact_path": plan["artifact_path"],
        "manifest": plan["manifest"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", metavar="ARTIFACT_DIR")
    parser.add_argument("--output-root")
    args = parser.parse_args()
    root = Path(args.root)

    if args.write:
        output_root = Path(args.output_root) if args.output_root else None
        result = materialize(root, output_root=output_root)
    elif args.check:
        result = validate_artifact(root, Path(args.check))
    else:
        result = _public_plan(build_plan(root))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

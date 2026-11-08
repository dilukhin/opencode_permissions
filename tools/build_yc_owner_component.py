"""Content-bound YC59 library component, never an enabled execution release."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DOMAIN = b"opencode_permissions.yc_owner_component.v1\n"
SOURCES = {
    "runtime/approval_owner/ledger.py": "runtime/approval_owner/ledger.py",
    "runtime/approval_owner/read_host.py": "runtime/approval_owner/read_host.py",
    "runtime/windows_owner_boundary.py": "tools/windows_owner_boundary.py",
    "runtime/windows_owner_pipe.py": "tools/windows_owner_pipe.py",
    "runtime/yc_snapshot_read.py": "tools/yc_snapshot_read.py",
    "runtime/yc_read_capture.py": "tools/yc_read_capture.py",
    "runtime/yc_read_projection.py": "tools/yc_read_projection.py",
    "runtime/yc_owner_native_veto.py": "tools/yc_owner_native_veto.py",
    "runtime/native_policy_matcher.py": "tools/native_policy_matcher.py",
    "runtime/render_native_policy.py": "tools/render_native_policy.py",
    "runtime/yc_policy_veto.py": "tools/yc_policy_veto.py",
    "policy/native/rules.v1.json": "policy/native/rules.v1.json",
    "policy/yc/yc_policy.v1.json": "policy/yc/yc_policy.v1.json",
}
GAPS = ["native_bootstrap_and_file_protection", "live_native_veto_authority",
        "trusted_read_context_and_spawn", "managed_activation_and_installed_acceptance"]


class ComponentError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def identity(core):
    return "sha256:" + hashlib.sha256(DOMAIN + canonical(core)).hexdigest()


def plan(root):
    root = Path(root)
    payloads = {}
    for dest, source in SOURCES.items():
        path = root / source
        if path.is_symlink() or not path.is_file():
            raise ComponentError("OWNER_COMPONENT_SOURCE_INVALID")
        payloads[dest] = path.read_bytes()
    core = {"schema": "yc-owner-component/v1", "owner": "dilukhin/opencode_permissions",
            "profile": "yc-snapshot-read/v1", "platform": "windows",
            "status": "library_only", "execution_enabled": False,
            "required_before_activation": GAPS,
            "files": [{"path": p, "sha256": hashlib.sha256(b).hexdigest(), "size": len(b)}
                      for p, b in sorted(payloads.items())]}
    return {"manifest": {**core, "artifact_id": identity(core)}, "payloads": payloads}


def validate(root, artifact):
    artifact = Path(artifact)
    expected = plan(root)
    manifest_bytes = canonical(expected["manifest"]) + b"\n"
    files = {**expected["payloads"], "manifest.json": manifest_bytes}
    if artifact.is_symlink() or not artifact.is_dir():
        raise ComponentError("OWNER_COMPONENT_DIRECTORY_INVALID")
    observed = set()
    for path in artifact.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ComponentError("OWNER_COMPONENT_SPECIAL_FILE")
        if path.is_file():
            relative = path.relative_to(artifact).as_posix()
            if relative not in files or path.read_bytes() != files[relative]:
                raise ComponentError("OWNER_COMPONENT_BYTES_MISMATCH")
            observed.add(relative)
    if observed != set(files):
        raise ComponentError("OWNER_COMPONENT_FILESET_MISMATCH")
    return expected["manifest"]


def materialize(root, output):
    data = plan(root)
    output = Path(output)
    # Builder writes only a fresh directory. It cannot repair/adopt an existing release.
    if output.exists() or output.is_symlink():
        raise ComponentError("OWNER_COMPONENT_OUTPUT_EXISTS")
    output.mkdir()
    files = {**data["payloads"], "manifest.json": canonical(data["manifest"]) + b"\n"}
    for relative, raw in files.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(raw)
    return validate(root, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", type=Path)
    mode.add_argument("--check", type=Path)
    args = parser.parse_args()
    result = materialize(args.root, args.write) if args.write else validate(args.root, args.check) if args.check else plan(args.root)["manifest"]
    print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    main()

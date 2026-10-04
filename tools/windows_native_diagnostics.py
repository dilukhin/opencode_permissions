#!/usr/bin/env python3
"""Install or remove a narrow project-local OpenCode 1.18.32 Windows rule fragment.

This is native permission configuration, not the P0 classifier. Existing
project configs are never edited, replaced, or silently merged.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ARTIFACT = Path(__file__).resolve().parents[1] / "policy" / "windows" / "native_diagnostics_1.18.32.json"
VERSION = "1.18.32"


def state(project: Path, payload: bytes) -> str:
    target = project / "opencode.json"
    if (project / "opencode.jsonc").exists():
        return "PROJECT_JSONC_CONFLICT"
    if target.is_symlink():
        return "PROJECT_CONFIG_SYMLINK"
    if not target.exists():
        return "ABSENT"
    if not target.is_file():
        return "PROJECT_CONFIG_NOT_FILE"
    return "INSTALLED" if target.read_bytes() == payload else "PROJECT_CONFIG_CONFLICT"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "enable", "disable"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--opencode", default="opencode")
    args = parser.parse_args()

    if os.name != "nt":
        print("WINDOWS_ONLY", file=sys.stderr)
        return 2
    if args.project.is_symlink() or not args.project.is_dir():
        print("INVALID_PROJECT_DIRECTORY", file=sys.stderr)
        return 2
    project = args.project.resolve(strict=True)
    payload = ARTIFACT.read_bytes()
    config = json.loads(payload)
    rules = config["permission"]["bash"]
    if list(rules.items()) != [
        ("*", "ask"),
        ("Get-Date -Format o", "allow"),
        ("[System.Environment]::OSVersion.VersionString", "allow"),
        ("Get-Location", "allow"),
    ]:
        print("INVALID_ARTIFACT", file=sys.stderr)
        return 2
    current = state(project, payload)

    if args.action == "status":
        print(json.dumps({"state": current, "project": str(project)}, ensure_ascii=False))
        return 0
    if args.action == "enable":
        if current == "INSTALLED":
            print("INSTALLED")
            return 0
        if current != "ABSENT":
            print(current, file=sys.stderr)
            return 2
        try:
            result = subprocess.run([args.opencode, "--version"], capture_output=True, text=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError):
            print("OPENCODE_VERSION_UNAVAILABLE", file=sys.stderr)
            return 2
        if result.stdout.strip() != VERSION:
            print("OPENCODE_VERSION_MISMATCH", file=sys.stderr)
            return 2
        target = project / "opencode.json"
        try:
            with target.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            print("PROJECT_CONFIG_CONFLICT", file=sys.stderr)
            return 2
        print("INSTALLED")
        return 0

    if current != "INSTALLED":
        print(current, file=sys.stderr)
        return 2
    (project / "opencode.json").unlink()
    print("DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only Stage 0 inventory for OpenCode Permissions.

The script intentionally avoids reading auth stores, logs, secret-like files, or
raw resolved provider configuration. It may optionally ask OpenCode to resolve
its config, but only when the installed CLI advertises --pure; only permission-
related fields are retained.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any

SECRETISH_NAMES = {
    "auth.json",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
}
CONFIG_NAMES = ("opencode.json", "opencode.jsonc")
CONFIG_DIR_NAMES = ("agents", "commands", "modes", "plugins", "skills", "tools", "themes")


def safe_file_meta(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return result
    result["is_file"] = path.is_file()
    result["is_dir"] = path.is_dir()
    if path.is_file():
        stat = path.stat()
        result["size"] = stat.st_size
        result["mtime_ns"] = stat.st_mtime_ns
    return result


def run_text(argv: list[str], *, cwd: Path | None = None, timeout: float = 10.0) -> dict[str, Any]:
    env = os.environ.copy()
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "true"
    try:
        cp = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error_type": type(exc).__name__}
    return {
        "ok": cp.returncode == 0,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


def command_version(executable: str | None) -> dict[str, Any]:
    if not executable:
        return {"present": False}
    result = run_text([executable, "--version"])
    version = result.get("stdout", "").strip().splitlines()
    return {
        "present": True,
        "path": executable,
        "version": version[0] if result.get("ok") and version else None,
        "version_probe_ok": bool(result.get("ok")),
    }


def help_capabilities(executable: str | None) -> dict[str, Any]:
    if not executable:
        return {}
    result = run_text([executable, "--help"])
    text = result.get("stdout", "") + "\n" + result.get("stderr", "")
    if not result.get("ok"):
        return {"help_probe_ok": False}
    return {
        "help_probe_ok": True,
        "supports_pure": "--pure" in text,
        "mentions_debug": "debug" in text,
        "mentions_auto": "--auto" in text,
    }


def infer_install_hint(path: str | None) -> dict[str, Any]:
    if not path:
        return {"hint": "not_found", "confidence": "none"}
    p = path.lower().replace("/", "\\")
    if "\\scoop\\" in p:
        return {"hint": "scoop", "confidence": "path_hint"}
    if "\\chocolatey\\" in p or "\\choco" in p:
        return {"hint": "chocolatey", "confidence": "path_hint"}
    if "\\npm\\" in p or "node_modules" in p:
        return {"hint": "npm_or_node", "confidence": "path_hint"}
    if ".local\\bin" in p or "/.local/bin" in path.lower():
        return {"hint": "user_local_or_script", "confidence": "path_hint"}
    return {"hint": "unknown", "confidence": "none"}


def git_root(project_dir: Path) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    result = run_text([git, "rev-parse", "--show-toplevel"], cwd=project_dir)
    if not result.get("ok"):
        return None
    lines = result.get("stdout", "").strip().splitlines()
    return lines[-1] if lines else None


def candidate_configs(project_dir: Path) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    home = Path.home()
    for name in CONFIG_NAMES:
        candidates.append(home / ".config" / "opencode" / name)

    env_config = os.environ.get("OPENCODE_CONFIG")
    if env_config:
        candidates.append(Path(env_config).expanduser())

    # Record project candidates from project_dir up to the nearest git root (inclusive),
    # or to filesystem root if no git root is available. No file content is read.
    root_text = git_root(project_dir)
    stop = Path(root_text).resolve() if root_text else None
    current = project_dir.resolve()
    while True:
        for name in CONFIG_NAMES:
            candidates.append(current / name)
            candidates.append(current / ".opencode" / name)
        if stop is not None and current == stop:
            break
        if current.parent == current:
            break
        current = current.parent

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for path in candidates:
        key = os.path.normcase(os.path.abspath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        result.append(safe_file_meta(path))
    return result


def opencode_dir_inventory(project_dir: Path) -> list[dict[str, Any]]:
    dirs = [Path.home() / ".config" / "opencode"]
    env_dir = os.environ.get("OPENCODE_CONFIG_DIR")
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    dirs.append(project_dir / ".opencode")

    result: list[dict[str, Any]] = []
    for base in dirs:
        item: dict[str, Any] = {"path": str(base), "exists": base.exists(), "subdirs": {}}
        if base.exists() and base.is_dir():
            for name in CONFIG_DIR_NAMES:
                sub = base / name
                # Filenames can reveal less than file contents and are useful for active layer discovery.
                names: list[str] = []
                if sub.exists() and sub.is_dir():
                    for child in sorted(sub.iterdir(), key=lambda p: p.name.lower()):
                        if child.name.lower() in SECRETISH_NAMES:
                            continue
                        names.append(child.name)
                item["subdirs"][name] = {"exists": sub.exists(), "entries": names}
        result.append(item)
    return result


def extract_permission_view(config: Any) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    result: dict[str, Any] = {}
    if "permission" in config:
        result["permission"] = config["permission"]
    if "permissions" in config:
        result["permissions"] = config["permissions"]
    if "default_agent" in config and isinstance(config["default_agent"], str):
        result["default_agent"] = config["default_agent"]
    agents = config.get("agent")
    if isinstance(agents, dict):
        agent_view: dict[str, Any] = {}
        for name, value in agents.items():
            if not isinstance(value, dict):
                continue
            subset: dict[str, Any] = {}
            if "permission" in value:
                subset["permission"] = value["permission"]
            if "permissions" in value:
                subset["permissions"] = value["permissions"]
            if "mode" in value and isinstance(value["mode"], str):
                subset["mode"] = value["mode"]
            if subset:
                agent_view[str(name)] = subset
        if agent_view:
            result["agent"] = agent_view
    return result


def resolved_permission_probe(executable: str | None, project_dir: Path, caps: dict[str, Any]) -> dict[str, Any]:
    if not executable:
        return {"status": "skipped", "reason": "opencode_not_found"}
    if not caps.get("supports_pure"):
        return {
            "status": "skipped",
            "reason": "installed_cli_does_not_advertise_--pure; avoid loading external plugins during audit",
        }
    result = run_text([executable, "--pure", "debug", "config"], cwd=project_dir, timeout=15.0)
    if not result.get("ok"):
        return {"status": "failed", "returncode": result.get("returncode")}
    stdout = result.get("stdout", "")
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {"status": "failed", "reason": "resolved_config_not_json; raw output intentionally discarded"}
    view = extract_permission_view(parsed)
    if view is None:
        return {"status": "failed", "reason": "unexpected_resolved_config_shape; raw output intentionally discarded"}
    return {"status": "ok", "permission_view": view}


def build_inventory(project_dir: Path, include_resolved_permissions: bool) -> dict[str, Any]:
    opencode = shutil.which("opencode")
    opencode2 = shutil.which("opencode2")
    caps = help_capabilities(opencode)
    env_presence = {
        "OPENCODE_CONFIG": bool(os.environ.get("OPENCODE_CONFIG")),
        "OPENCODE_CONFIG_DIR": bool(os.environ.get("OPENCODE_CONFIG_DIR")),
        "OPENCODE_CONFIG_CONTENT": bool(os.environ.get("OPENCODE_CONFIG_CONTENT")),
        "OPENCODE_GIT_BASH_PATH": bool(os.environ.get("OPENCODE_GIT_BASH_PATH")),
        "OPENCODE_DISABLE_AUTOUPDATE": bool(os.environ.get("OPENCODE_DISABLE_AUTOUPDATE")),
    }
    data: dict[str, Any] = {
        "schema": 1,
        "audit_mode": "read_only_inventory",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "project": {
            "requested_dir": str(project_dir.resolve()),
            "git_root": git_root(project_dir),
        },
        "binaries": {
            "opencode": command_version(opencode),
            "opencode2": command_version(opencode2),
        },
        "opencode_capabilities": caps,
        "install_method": infer_install_hint(opencode),
        "shell": {
            "COMSPEC": os.environ.get("COMSPEC"),
            "git_bash_path": os.environ.get("OPENCODE_GIT_BASH_PATH"),
            "bash": shutil.which("bash"),
            "pwsh": shutil.which("pwsh"),
            "powershell": shutil.which("powershell"),
            "cmd": shutil.which("cmd"),
        },
        "environment_presence": env_presence,
        "config_candidates": candidate_configs(project_dir),
        "config_directories": opencode_dir_inventory(project_dir),
        "safety": {
            "auth_store_read": False,
            "log_files_read": False,
            "config_file_contents_read": False,
            "raw_resolved_config_retained": False,
            "autoupdate_disabled_for_subprocess_probes": True,
        },
    }
    if include_resolved_permissions:
        data["resolved_permissions"] = resolved_permission_probe(opencode, project_dir, caps)
    else:
        data["resolved_permissions"] = {"status": "not_requested"}
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OpenCode Stage 0 inventory")
    parser.add_argument("--project-dir", default=".", help="Project directory to inspect (default: current directory)")
    parser.add_argument("--output", help="Write JSON result to this file instead of stdout")
    parser.add_argument(
        "--resolved-permissions",
        action="store_true",
        help="Use `opencode --pure debug config` when supported and retain only permission-related fields",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser()
    if not project_dir.exists() or not project_dir.is_dir():
        print("project directory does not exist or is not a directory", file=sys.stderr)
        return 2

    data = build_inventory(project_dir, args.resolved_permissions)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

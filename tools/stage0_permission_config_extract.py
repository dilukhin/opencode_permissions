#!/usr/bin/env python3
"""Sanitized local permission-config extractor for Stage 0.

The tool reads only recognized OpenCode config files from explicitly selected
locations and emits only permission-related fields. Raw config text and
permission-bearing environment variable values are never written to output.

This is intentionally separate from stage0_inventory.py: the inventory's
minimal 0A.1 contract remains metadata-only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from stage0_inventory import extract_permission_view, safe_file_meta


GLOBAL_CONFIG_NAMES = ("config.json", "opencode.json", "opencode.jsonc")
MANAGED_CONFIG_NAMES = ("opencode.json", "opencode.jsonc")
ALLOWED_CONFIG_NAMES = frozenset(GLOBAL_CONFIG_NAMES)
PERMISSION_ENV_NAMES = (
    "OPENCODE_CONFIG",
    "OPENCODE_CONFIG_DIR",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_DISABLE_PROJECT_CONFIG",
    "OPENCODE_PERMISSION",
)

SECRETISH_MARKERS = (
    "authorization:",
    "bearer ",
    "api_key=",
    "apikey=",
    "token=",
    "password=",
    "-----begin private key-----",
    "github_pat_",
    "ghp_",
)


def strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments while preserving quoted strings/newlines."""
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            out.extend((" ", " "))
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            out.extend((" ", " "))
            i += 2
            while i < len(text):
                ch2 = text[i]
                nxt2 = text[i + 1] if i + 1 < len(text) else ""
                if ch2 == "*" and nxt2 == "/":
                    out.extend((" ", " "))
                    i += 2
                    break
                out.append(ch2 if ch2 in "\r\n" else " ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_trailing_commas(text: str) -> str:
    """Remove JSONC trailing commas outside quoted strings."""
    chars = list(text)
    i = 0
    in_string = False
    escaped = False
    while i < len(chars):
        ch = chars[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(chars) and chars[j].isspace():
                j += 1
            if j < len(chars) and chars[j] in "]}":
                chars[i] = " "
        i += 1
    return "".join(chars)


def parse_json_or_jsonc(text: str) -> Any:
    normalized = strip_trailing_commas(strip_jsonc_comments(text.lstrip("\ufeff")))
    return json.loads(normalized)


def secretish(value: Any) -> bool:
    if isinstance(value, str):
        low = value.lower()
        return any(marker in low for marker in SECRETISH_MARKERS)
    if isinstance(value, list):
        return any(secretish(item) for item in value)
    if isinstance(value, dict):
        return any(secretish(key) or secretish(item) for key, item in value.items())
    return False


def extract_source(path: Path) -> dict[str, Any]:
    meta = safe_file_meta(path)
    result: dict[str, Any] = {"path": str(path), "metadata": meta}
    if path.name not in ALLOWED_CONFIG_NAMES:
        result.update({"status": "refused", "reason": "unsupported_config_filename"})
        return result
    if not path.exists():
        result["status"] = "not_found"
        return result
    if not path.is_file():
        result.update({"status": "refused", "reason": "not_a_regular_file"})
        return result
    if path.is_symlink():
        result.update({"status": "refused", "reason": "symlink_not_allowed"})
        return result

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        result.update({"status": "read_failed", "error_type": type(exc).__name__})
        return result

    try:
        parsed = parse_json_or_jsonc(raw)
    except json.JSONDecodeError as exc:
        result.update(
            {
                "status": "parse_failed",
                "error_type": "JSONDecodeError",
                "line": exc.lineno,
                "column": exc.colno,
            }
        )
        return result
    finally:
        raw = ""  # make accidental later retention less likely

    view = extract_permission_view(parsed)
    parsed = None
    if view is None:
        result.update({"status": "parse_failed", "reason": "top_level_config_not_object"})
        return result
    if secretish(view):
        result.update({"status": "refused", "reason": "secretish_marker_in_permission_view"})
        return result
    result.update({"status": "ok", "permission_view": view})
    return result


def managed_config_dir() -> Path:
    override = os.environ.get("OPENCODE_TEST_MANAGED_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "opencode"
    if sys.platform == "darwin":
        return Path("/Library/Application Support/opencode")
    return Path("/etc/opencode")


def permission_environment_presence() -> dict[str, bool]:
    """Return presence only; never expose environment variable values."""
    return {name: bool(os.environ.get(name)) for name in PERMISSION_ENV_NAMES}


def selected_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    if args.user_global_defaults:
        base = Path.home() / ".config" / "opencode"
        paths.extend(base / name for name in GLOBAL_CONFIG_NAMES)
    if args.managed_defaults:
        base = managed_config_dir()
        paths.extend(base / name for name in MANAGED_CONFIG_NAMES)
    paths.extend(Path(item).expanduser() for item in (args.config or []))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = os.path.normcase(os.path.abspath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def build_output(paths: list[Path]) -> dict[str, Any]:
    return {
        "schema": 2,
        "audit_mode": "sanitized_permission_config_extract",
        "source_order": (
            "argument selection order; --user-global-defaults uses config.json -> opencode.json -> opencode.jsonc; "
            "--managed-defaults uses managed opencode.json -> opencode.jsonc after user/global/project/account layers"
        ),
        "environment_presence": permission_environment_presence(),
        "sources": [extract_source(path) for path in paths],
        "raw_config_retained": False,
        "environment_values_retained": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract only permission/default-agent fields from recognized OpenCode JSON/JSONC config files."
    )
    parser.add_argument(
        "--user-global-defaults",
        action="store_true",
        help="Read standard ~/.config/opencode/config.json, opencode.json and opencode.jsonc in runtime load order.",
    )
    parser.add_argument(
        "--managed-defaults",
        action="store_true",
        help="Read standard managed opencode.json/opencode.jsonc candidates for this platform.",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="PATH",
        help="Explicit recognized config.json/opencode.json/opencode.jsonc path; may be repeated.",
    )
    parser.add_argument("--output", type=Path, help="Write sanitized JSON here instead of stdout.")
    args = parser.parse_args(argv)

    paths = selected_paths(args)
    if not paths:
        parser.error("select at least one source with --user-global-defaults, --managed-defaults or --config PATH")

    data = build_output(paths)
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

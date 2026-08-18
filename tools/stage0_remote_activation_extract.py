#!/usr/bin/env python3
"""Stage 0 presence-only detector for remote permission-config activation.

The detector never emits auth tokens, provider/server identifiers, account IDs,
organization IDs, remote URLs, or raw secret-bearing records. It only answers
whether the two OpenCode 1.18.18 remote-config activation paths can be active:
well-known auth and an active account organization.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any


def data_dir() -> tuple[Path, str]:
    override = os.environ.get("XDG_DATA_HOME")
    if override:
        return Path(override).expanduser() / "opencode", "XDG_DATA_HOME"
    return Path.home() / ".local" / "share" / "opencode", "home_default"


def safe_meta(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return result
    result["is_file"] = path.is_file()
    result["is_dir"] = path.is_dir()
    result["is_symlink"] = path.is_symlink()
    if path.is_file():
        try:
            result["size"] = path.stat().st_size
        except OSError:
            pass
    return result


def inspect_auth(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": "auth.json",
        "metadata": safe_meta(path),
        "wellknown_auth_present": False,
        "secret_values_retained": False,
    }
    if os.environ.get("OPENCODE_AUTH_CONTENT"):
        result.update(
            {
                "status": "blocked_env_override",
                "wellknown_auth_present": None,
                "reason": "OPENCODE_AUTH_CONTENT present; value intentionally not inspected",
            }
        )
        return result
    if not path.exists():
        result["status"] = "not_found"
        return result
    if not path.is_file() or path.is_symlink():
        result.update({"status": "refused", "wellknown_auth_present": None, "reason": "auth source is not a regular file"})
        return result
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        result.update(
            {
                "status": "parse_failed",
                "wellknown_auth_present": None,
                "error_type": "JSONDecodeError",
                "line": exc.lineno,
                "column": exc.colno,
            }
        )
        return result
    except (OSError, UnicodeError) as exc:
        result.update({"status": "read_failed", "wellknown_auth_present": None, "error_type": type(exc).__name__})
        return result

    if not isinstance(parsed, dict):
        result.update({"status": "parse_failed", "wellknown_auth_present": None, "reason": "top_level_not_object"})
        return result

    result["wellknown_auth_present"] = any(
        isinstance(value, dict) and value.get("type") == "wellknown" for value in parsed.values()
    )
    parsed = None
    result["status"] = "ok"
    return result


def inspect_database(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": path.name,
        "metadata": safe_meta(path),
        "active_account_present": False,
        "active_org_present": False,
        "identifier_values_retained": False,
    }
    if not path.exists():
        result["status"] = "not_found"
        return result
    if not path.is_file() or path.is_symlink():
        result.update(
            {
                "status": "refused",
                "active_account_present": None,
                "active_org_present": None,
                "reason": "database source is not a regular file",
            }
        )
        return result

    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            row = connection.execute(
                "SELECT active_account_id, active_org_id FROM account_state WHERE id = 1 LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "no such table" in message:
            result["status"] = "schema_absent"
            return result
        result.update(
            {
                "status": "read_failed",
                "active_account_present": None,
                "active_org_present": None,
                "error_type": "OperationalError",
            }
        )
        return result
    except (OSError, sqlite3.DatabaseError) as exc:
        result.update(
            {
                "status": "read_failed",
                "active_account_present": None,
                "active_org_present": None,
                "error_type": type(exc).__name__,
            }
        )
        return result

    result["status"] = "ok"
    if row:
        result["active_account_present"] = row[0] is not None
        result["active_org_present"] = row[1] is not None
    return result


def database_candidates(root: Path) -> tuple[list[Path], str]:
    override = os.environ.get("OPENCODE_DB")
    if override:
        if override == ":memory:":
            return [], "memory_override"
        value = Path(override).expanduser()
        if not value.is_absolute():
            value = root / value
        return [value], "OPENCODE_DB"
    if not root.exists() or not root.is_dir():
        return [], "default_glob"
    return sorted(root.glob("opencode*.db"), key=lambda item: item.name.casefold()), "default_glob"


def aggregate_active_org(databases: list[dict[str, Any]], source_mode: str) -> tuple[bool | None, str]:
    if source_mode == "memory_override":
        return None, "OPENCODE_DB=:memory: cannot be inspected out of process"
    values = [item.get("active_org_present") for item in databases]
    if any(value is True for value in values):
        return True, "active organization found in a candidate runtime database"
    if any(value is None for value in values):
        return None, "at least one candidate runtime database could not be determined safely"
    return False, "no active organization found in candidate runtime databases"


def build_output() -> dict[str, Any]:
    root, root_source = data_dir()
    auth = inspect_auth(root / "auth.json")
    candidates, db_source = database_candidates(root)
    databases = [inspect_database(path) for path in candidates]
    active_org, active_org_reason = aggregate_active_org(databases, db_source)
    wellknown = auth.get("wellknown_auth_present")
    fully_determined = isinstance(wellknown, bool) and isinstance(active_org, bool)
    remote_active: bool | None
    if wellknown is True or active_org is True:
        remote_active = True
    elif fully_determined:
        remote_active = False
    else:
        remote_active = None

    return {
        "schema": 1,
        "audit_mode": "stage0_remote_config_activation_presence_only",
        "target_semantics": "OpenCode 1.18.18",
        "data_root": {
            "source": root_source,
            "path": str(root),
            "XDG_DATA_HOME_present": bool(os.environ.get("XDG_DATA_HOME")),
        },
        "environment_presence": {
            "OPENCODE_AUTH_CONTENT": bool(os.environ.get("OPENCODE_AUTH_CONTENT")),
            "OPENCODE_DB": bool(os.environ.get("OPENCODE_DB")),
        },
        "auth": auth,
        "account_database_source": db_source,
        "account_databases": databases,
        "remote_activation": {
            "wellknown_remote_possible": wellknown,
            "account_remote_possible": active_org,
            "account_remote_reason": active_org_reason,
            "remote_permission_layer_activation_observed": remote_active,
            "fully_determined": fully_determined,
        },
        "raw_auth_retained": False,
        "secret_values_retained": False,
        "account_identifier_values_retained": False,
        "environment_values_retained": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Presence-only Stage 0 detector for OpenCode remote config activation")
    parser.add_argument("--output", type=Path, required=True, help="Write sanitized JSON to this file")
    args = parser.parse_args(argv)

    payload = build_output()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

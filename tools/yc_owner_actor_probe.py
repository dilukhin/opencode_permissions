"""Read-only Windows actor observation. Never authorizes or executes YC.

Only the explicitly requested new report is written. No subprocess, network,
configuration/credential reads, account changes, memory writes or deployment.
"""
import sys
sys.dont_write_bytecode = True

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from windows_owner_boundary import BoundaryError, Principal, admit, current


def observe(role, *, counterpart=None):
    actor = current()
    result = {"schema": "yc59-windows-actor-observation/v1", "role_label": role,
        "observed_at": datetime.now(timezone.utc).isoformat(), "actor": asdict(actor),
        "identity_source": "current_process_TokenUser_and_TokenSessionId",
        "stdin_is_terminal": sys.stdin.isatty(), "stdout_is_terminal": sys.stdout.isatty(),
        "python_version": sys.version.split()[0], "python_path": sys.executable,
        "python_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "status": "BLOCKED_COUNTERPART_NOT_OBSERVED", "deployment_ready": False,
        "report_is_authorization": False, "cloud_invocations": 0, "child_processes": 0,
        "account_or_config_changes": 0}
    if counterpart is not None:
        if (type(counterpart) is not dict or counterpart.get("schema") != result["schema"]
                or counterpart.get("role_label") not in {"owner", "agent"}
                or counterpart["role_label"] == role):
            raise BoundaryError("COUNTERPART_REPORT_INVALID")
        observed = counterpart.get("actor")
        if type(observed) is not dict or set(observed) != {"sid", "session_id"}:
            raise BoundaryError("COUNTERPART_REPORT_INVALID")
        other = Principal(**observed)
        owner, agent = (actor, other) if role == "owner" else (other, actor)
        try:
            admit(owner, agent, agent.sid)
            result["status"] = "CANDIDATE_SEPARATE_SESSIONS_OBSERVED"
        except BoundaryError as error:
            result["status"] = "BLOCKED_ACTOR_BOUNDARY"
            result["reason"] = str(error)
        result["comparison_is_executor_evidence_only"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("agent", "owner"), required=True)
    parser.add_argument("--counterpart", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("WINDOWS_REQUIRED")
    other = None if args.counterpart is None else json.loads(args.counterpart.read_text(encoding="utf-8"))
    result = observe(args.role, counterpart=other)
    # Existing output is never replaced. Parent must be the explicitly chosen task directory.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print(result["status"])


if __name__ == "__main__":
    main()

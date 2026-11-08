"""Experimental Windows owner terminal. No execution and no automatic decision.

Requires a separately authenticated owner OS account and trusted bootstrap.
TTY alone is not evidence of human origin. Do not run OpenCode under that SID.
"""
import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import windows_owner_boundary as boundary


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))
from approval_owner.console import review

def main():
    if os.name != "nt" or not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("OWNER_WINDOWS_TERMINAL_REQUIRED")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipe", required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--operation-sha256", required=True)
    parser.add_argument("--agent-sid", required=True)
    args = parser.parse_args()
    from pipe_transport import call
    review(lambda request: call(args.pipe, request, args.server_pid), args.request_id,
           args.operation_sha256, terminal=True, owner_actor=boundary.current(), agent_sid=args.agent_sid)


if __name__ == "__main__":
    main()

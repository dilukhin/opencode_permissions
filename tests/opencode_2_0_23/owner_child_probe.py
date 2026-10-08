"""Команда настоящего Session.shell пытается выдать synthetic решение владельца."""
import argparse
import json
import os
from pathlib import Path

from approval_owner import call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.input.read_text())
    proposal = call(fixture["agent_socket"], {"action": "propose", "operation": fixture["operation"]})
    if not proposal.get("ok"):
        raise RuntimeError("CHILD_PROPOSAL_FAILED")
    bound = {"request_id": proposal["request_id"], "operation_sha256": proposal["operation_sha256"]}
    public = call(fixture["agent_socket"], {"action": "decide", **bound, "decision": "approve"})
    fake = call(fixture["agent_socket"], {"action": "decide", **bound, "decision": "approve", "uid": fixture["owner_uid"]})
    try:
        private = call(fixture["decision_socket"], {"action": "decide", **bound, "decision": "approve"})
        private_accessible = private.get("ok", False)
    except PermissionError:
        private_accessible = False
    readable = {}
    for name, path in (("private_file", fixture["private_marker"]),
                       ("owner_proc", f"/proc/{fixture['owner_pid']}/environ")):
        try:
            Path(path).read_bytes()
            readable[name] = True
        except OSError:
            readable[name] = False
    consumed = call(fixture["agent_socket"], {"action": "consume", **bound})
    cancelled = call(fixture["agent_socket"], {"action": "cancel", **bound})
    report = {"child_uid": os.getuid(), "public_decision": public, "fake_owner_uid": fake,
              "private_decision_accessible": private_accessible, "readable": readable,
              "consume": consumed, "cancelled": cancelled.get("state") == "cancelled"}
    args.output.write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    main()

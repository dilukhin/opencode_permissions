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


def review(call, request_id, digest, *, terminal, read_line=input, write_line=print):
    if not terminal:
        raise ValueError("OWNER_TERMINAL_REQUIRED")
    try:
        valid = str(uuid.UUID(request_id)) == request_id
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid or type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("OWNER_REVIEW_BINDING_INVALID")
    bound = {"request_id": request_id, "operation_sha256": digest}
    inspected = call({"action": "inspect", **bound})
    if not inspected.get("ok") or inspected.get("state") != "pending":
        raise ValueError("OWNER_REQUEST_NOT_PENDING")
    operation = inspected.get("operation", {})
    if operation.get("schema") != "yc-snapshot-read/v1" or operation.get("action") != "yc.snapshot.read":
        raise ValueError("OWNER_READ_PROFILE_REQUIRED")
    if inspected.get("request_id") != request_id or inspected.get("operation_sha256") != digest:
        raise ValueError("OWNER_REVIEW_BINDING_CHANGED")
    write_line("Испытательный запрос: прочитать ВМ, диск и снимок по точным ID.")
    write_line("Облачные ресурсы не изменяются. Ответ ограничивается проверенными полями.")
    write_line("Готовность снимка не доказывает возможность восстановления.")
    # Escape every untrusted/control/bidi character before displaying bindings.
    write_line(json.dumps(operation, ensure_ascii=True, sort_keys=True, indent=2))
    write_line("SHA-256 запроса: " + digest)
    expected = "РАЗРЕШИТЬ ОДИН РАЗ " + request_id
    choice = read_line("Для согласия введите «" + expected + "». Любой другой ответ — отказ: ")
    decision = "approve" if choice == expected else "reject"
    result = call({"action": "decide", **bound, "decision": decision})
    if (not result.get("ok") or result.get("owner_instance_id") != inspected.get("owner_instance_id")
            or result.get("request_id") != request_id or result.get("operation_sha256") != digest
            or result.get("state") != ("approved" if decision == "approve" else "rejected")):
        raise ValueError("OWNER_DECISION_NOT_RECORDED")
    write_line("Решение записано для этого запроса. Исполнение эта консоль не запускает.")
    return decision


def main():
    if os.name != "nt" or not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("OWNER_WINDOWS_TERMINAL_REQUIRED")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipe", required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--operation-sha256", required=True)
    args = parser.parse_args()
    from pipe_transport import call
    review(lambda request: call(args.pipe, request, args.server_pid), args.request_id,
           args.operation_sha256, terminal=True)


if __name__ == "__main__":
    main()

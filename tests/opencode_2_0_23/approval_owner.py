"""Испытательный Linux-владелец согласия. Не исполняет команды или SSH."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import socket
import struct
import sys
import threading
import time
import uuid


class Refusal(Exception):
    pass


def strict_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise Refusal("DUPLICATE_KEY")
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(Refusal("INVALID_JSON")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refusal("INVALID_JSON") from error
    if not isinstance(value, dict):
        raise Refusal("OBJECT_REQUIRED")
    return value


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise Refusal("UNEXPECTED_FIELDS")


def canonical(operation):
    keys(operation, ("schema", "action", "job_id", "transaction_id", "command", "command_sha256",
                     "argv", "executable", "cwd", "ssh_identity", "policy_revision", "execution_host_id"))
    if type(operation["schema"]) is not int or operation["schema"] != 1:
        raise Refusal("BAD_SCHEMA")
    if operation["action"] not in ("sudo_job.start", "sudo_job.stop"):
        raise Refusal("BAD_ACTION")
    for name in ("job_id", "transaction_id", "execution_host_id"):
        try:
            if str(uuid.UUID(operation[name])) != operation[name]:
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as error:
            raise Refusal("BAD_UUID") from error
    for name in ("command", "executable", "cwd", "policy_revision"):
        value = operation[name]
        if not isinstance(value, str) or not value or "\0" in value or len(value) > 8192:
            raise Refusal("BAD_TEXT")
    if not Path(operation["executable"]).is_absolute() or not Path(operation["cwd"]).is_absolute():
        raise Refusal("ABSOLUTE_PATH_REQUIRED")
    if not isinstance(operation["argv"], list) or not operation["argv"] or len(operation["argv"]) > 64:
        raise Refusal("BAD_ARGV")
    if any(not isinstance(x, str) or "\0" in x or len(x) > 8192 for x in operation["argv"]):
        raise Refusal("BAD_ARGV")
    if operation["argv"][0] != operation["executable"]:
        raise Refusal("EXECUTABLE_MISMATCH")
    try:
        command_hash = hashlib.sha256(operation["command"].encode("utf-8")).hexdigest()
        if operation["command_sha256"] != command_hash:
            raise Refusal("COMMAND_HASH_MISMATCH")
        identity = operation["ssh_identity"]
        keys(identity, ("remote_host", "remote_port", "remote_user", "host_key_algorithm",
                        "remote_host_key_sha256", "daemon_instance_id", "connection_generation"))
        if type(identity["remote_port"]) is not int or not 1 <= identity["remote_port"] <= 65535:
            raise Refusal("BAD_SSH_IDENTITY")
        if type(identity["connection_generation"]) is not int or identity["connection_generation"] < 1:
            raise Refusal("BAD_SSH_IDENTITY")
        if any(not isinstance(identity[x], str) or not identity[x] or "\0" in identity[x]
               for x in ("remote_host", "remote_user", "host_key_algorithm", "daemon_instance_id")):
            raise Refusal("BAD_SSH_IDENTITY")
        if not isinstance(identity["remote_host_key_sha256"], str) or not re.fullmatch(
            r"SHA256:[A-Za-z0-9+/]{43}", identity["remote_host_key_sha256"],
        ):
            raise Refusal("BAD_SSH_IDENTITY")
        return json.dumps(operation, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise Refusal("INVALID_OPERATION") from error


class Ledger:
    def __init__(self, owner_uid, agent_uids, policy_revision, execution_host_id, *, ttl=60,
                 blocked_hashes=(), clock=time.monotonic):
        if owner_uid in agent_uids or not agent_uids or ttl <= 0:
            raise Refusal("AUTHORITY_NOT_SEPARATE")
        self.owner_uid, self.agent_uids = owner_uid, frozenset(agent_uids)
        self.policy_revision, self.execution_host_id = policy_revision, execution_host_id
        self.ttl, self.clock, self.blocked_hashes = ttl, clock, frozenset(blocked_hashes)
        self.instance = str(uuid.uuid4())
        self.entries = {}
        self.lock = threading.Lock()
        self.closed = False

    def handle(self, channel, uid, request):
        # uid берётся исключительно из SO_PEERCRED сервером, не из JSON.
        with self.lock:
            if self.closed:
                raise Refusal("OWNER_CLOSED")
            if channel == "decision":
                if uid != self.owner_uid:
                    raise Refusal("NOT_DECISION_OWNER")
                if request.get("action") == "inspect":
                    keys(request, ("action", "request_id", "operation_sha256"))
                    entry = self._entry(request)
                    return {**self._view(entry), "operation": strict_json(entry["operation"])}
                keys(request, ("action", "request_id", "operation_sha256", "decision"))
                if request["action"] != "decide" or request["decision"] not in ("approve", "reject"):
                    raise Refusal("BAD_DECISION")
                entry = self._entry(request)
                if entry["state"] != "pending":
                    raise Refusal("DECISION_ALREADY_FINAL")
                entry["state"] = "approved" if request["decision"] == "approve" else "rejected"
                return self._view(entry)
            if channel != "agent" or uid not in self.agent_uids:
                raise Refusal("NOT_AGENT")
            action = request.get("action")
            if action == "propose":
                keys(request, ("action", "operation"))
                raw = canonical(request["operation"])
                operation = strict_json(raw)
                if operation["policy_revision"] != self.policy_revision:
                    raise Refusal("POLICY_CHANGED")
                if operation["execution_host_id"] != self.execution_host_id:
                    raise Refusal("HOST_CHANGED")
                if operation["command_sha256"] in self.blocked_hashes:
                    raise Refusal("POLICY_DENY")
                if len(self.entries) >= 128:
                    raise Refusal("OWNER_CAPACITY")
                entry = {"request_id": str(uuid.uuid4()), "operation_sha256": hashlib.sha256(raw).hexdigest(),
                         "operation": raw, "uid": uid, "state": "pending", "deadline": self.clock() + self.ttl}
                self.entries[entry["request_id"]] = entry
                return self._view(entry)
            if action not in ("inspect", "cancel", "consume"):
                raise Refusal("AGENT_CANNOT_DECIDE")
            keys(request, ("action", "request_id", "operation_sha256"))
            entry = self._entry(request)
            if entry["uid"] != uid:
                raise Refusal("WRONG_CALLER")
            if action == "cancel":
                if entry["state"] not in ("pending", "approved"):
                    raise Refusal("ALREADY_FINAL")
                entry["state"] = "cancelled"
            if action == "consume":
                if entry["state"] != "approved":
                    raise Refusal("APPROVAL_REQUIRED")
                # Однократное потребление происходит до возврата ответа.
                entry["state"] = "consumed"
            return self._view(entry)

    def _entry(self, request):
        if not isinstance(request["request_id"], str):
            raise Refusal("UNKNOWN_REQUEST")
        entry = self.entries.get(request["request_id"])
        if entry is None:
            raise Refusal("UNKNOWN_REQUEST")
        if request["operation_sha256"] != entry["operation_sha256"]:
            raise Refusal("OPERATION_CHANGED")
        if entry["state"] in ("pending", "approved") and self.clock() >= entry["deadline"]:
            entry["state"] = "expired"
        if entry["state"] == "expired":
            raise Refusal("REQUEST_EXPIRED")
        return entry

    def _view(self, entry):
        return {"request_id": entry["request_id"], "operation_sha256": entry["operation_sha256"],
                "owner_instance_id": self.instance, "state": entry["state"]}

    def close(self):
        with self.lock:
            self.closed = True
            for entry in self.entries.values():
                if entry["state"] in ("pending", "approved"):
                    entry["state"] = "cancelled"


def call(address, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(str(address))
        connection.sendall(json.dumps(request).encode() + b"\n")
        with connection.makefile("rb") as stream:
            return strict_json(stream.readline(65537))


def serve(args):
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise Refusal("LINUX_PEER_CREDENTIALS_REQUIRED")
    if os.getuid() == 0 or os.getuid() in args.agent_uid:
        raise Refusal("OWNER_UID_REQUIRED")
    for address, private in ((args.agent_socket, False), (args.decision_socket, True)):
        parent = address.parent.stat()
        if parent.st_uid != os.getuid() or parent.st_mode & 0o022 or (private and parent.st_mode & 0o077):
            raise Refusal("UNSAFE_SOCKET_DIRECTORY")
    ledger = Ledger(os.getuid(), args.agent_uid, args.policy_revision, args.host_id)
    selector = selectors.DefaultSelector()
    listeners = []
    for address, channel, mode in ((args.agent_socket, "agent", 0o666), (args.decision_socket, "decision", 0o600)):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(address))
        address.chmod(mode)
        listener.listen(8)
        listeners.append(listener)
        selector.register(listener, selectors.EVENT_READ, channel)
    print(json.dumps({"owner_ready": True, "owner_instance_id": ledger.instance}), flush=True)
    try:
        while True:
            for key, _ in selector.select(timeout=0.2):
                connection, _ = key.fileobj.accept()
                with connection:
                    connection.settimeout(2)
                    _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    try:
                        with connection.makefile("rb") as stream:
                            raw = stream.readline(65537)
                        if not raw.endswith(b"\n") or len(raw) > 65536:
                            raise Refusal("INPUT_LIMIT")
                        result = {"ok": True, **ledger.handle(key.data, uid, strict_json(raw))}
                    except (Refusal, OSError) as error:
                        result = {"ok": False, "code": str(error) if isinstance(error, Refusal) else "TRANSPORT_ERROR"}
                    connection.sendall(json.dumps(result).encode() + b"\n")
    finally:
        ledger.close()
        selector.close()
        for listener in listeners:
            listener.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--agent-socket", type=Path, required=True)
    server.add_argument("--decision-socket", type=Path, required=True)
    server.add_argument("--agent-uid", type=int, action="append", required=True)
    server.add_argument("--policy-revision", required=True)
    server.add_argument("--host-id", required=True)
    client = sub.add_parser("call")
    client.add_argument("--socket", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "serve":
        serve(args)
    else:
        print(json.dumps(call(args.socket, strict_json(sys.stdin.buffer.readline(65537)))))


if __name__ == "__main__":
    main()

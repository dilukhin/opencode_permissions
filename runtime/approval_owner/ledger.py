"""Process-lifetime approval automaton extracted from the pinned #47 owner.

One authority, no transport, public approve CLI, persistence or executor.
A composition root MUST supply the exact trusted profile canonicalizer.
"""
from __future__ import annotations
import hashlib
import json
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


class Ledger:
    def __init__(self, owner_uid, agent_uids, policy_revision, execution_host_id, *, ttl=60,
                 blocked_hashes=(), clock=time.monotonic, canonicalizer,
                 consume_check=None):
        if owner_uid in agent_uids or not agent_uids or ttl <= 0:
            raise Refusal("AUTHORITY_NOT_SEPARATE")
        self.owner_uid, self.agent_uids = owner_uid, frozenset(agent_uids)
        self.policy_revision, self.execution_host_id = policy_revision, execution_host_id
        self.ttl, self.clock, self.blocked_hashes = ttl, clock, frozenset(blocked_hashes)
        self.instance = str(uuid.uuid4())
        # Trusted composition-root callbacks only; never request/JSON fields.
        if not callable(canonicalizer) or (consume_check is not None and not callable(consume_check)):
            raise Refusal("TRUSTED_PROFILE_REQUIRED")
        self.canonicalizer, self.consume_check = canonicalizer, consume_check
        self.entries = {}
        self.lock = threading.Lock()
        self.closed = False

    def handle(self, channel, uid, request):
        # uid is supplied by authenticated OS transport, never by request JSON.
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
                raw = self.canonicalizer(request["operation"])
                if type(raw) is not bytes or len(raw) > 65536:
                    raise Refusal("PROFILE_OUTPUT_INVALID")
                operation = strict_json(raw)
                if operation["policy_revision"] != self.policy_revision:
                    raise Refusal("POLICY_CHANGED")
                if operation["execution_host_id"] != self.execution_host_id:
                    raise Refusal("HOST_CHANGED")
                if self.blocked_hashes and "command_sha256" not in operation:
                    raise Refusal("DENY_PROFILE_UNSUPPORTED")
                if operation.get("command_sha256") in self.blocked_hashes:
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
                if self.consume_check is not None:
                    try:
                        self.consume_check(entry["operation"])
                    except Exception:
                        entry["state"] = "cancelled"
                        raise Refusal("CONSUME_CONTEXT_CHANGED") from None
                    # A slow trusted check must not extend the original deadline.
                    if self.clock() >= entry["deadline"]:
                        entry["state"] = "expired"
                        raise Refusal("REQUEST_EXPIRED")
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

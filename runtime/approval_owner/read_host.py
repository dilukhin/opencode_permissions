"""Exact-read host composition; no standalone launcher or approval CLI.

The bootstrap must supply protected live context, native veto and starter.
These inputs are constructor-only, never fields of the pipe protocol.
"""
from __future__ import annotations

import json
import queue
import threading

from .ledger import Ledger, Refusal, strict_json
import windows_owner_boundary as boundary
from yc_read_projection import ProjectionError
from yc_snapshot_read import ReadError, ReadProfile, dispatch_read
from windows_owner_pipe import Transport


class ReadHost:
    def __init__(self, prefix, agent_sid, *, current_context, native_check, start):
        self.owner, self.agent_sid = boundary.current(), agent_sid
        self.stopping = threading.Event()
        if not callable(start):
            raise ReadError("YC_READ_STARTER_REQUIRED")
        self.profile = ReadProfile(current_context, native_check)
        operation = self.profile.operation()
        self.ledger = Ledger(self.owner.sid, [agent_sid], operation["policy_revision"],
                             operation["execution_host_id"], canonicalizer=self.profile.canonicalize,
                             consume_check=self.profile.check_consumption)
        def guarded_start(execution, argv):
            if self.stopping.is_set():
                raise ReadError("YC_READ_HOST_CLOSED")
            return start(execution, argv)
        self.start, self.origins, self.origin_lock = guarded_start, {}, threading.Lock()
        self.pending = queue.Queue(maxsize=128)
        try:
            self.transport = Transport(prefix, agent_sid, self.handle)
        except BaseException:
            self.ledger.close()
            raise

    def handle(self, channel, principal, raw):
        try:
            boundary.validate(principal)
            if channel == "agent":
                boundary.admit(self.owner, principal, self.agent_sid)
            elif channel != "decision" or principal != self.owner:
                raise Refusal("NOT_DECISION_OWNER")
            if self.stopping.is_set():
                raise Refusal("OWNER_CLOSED")
            request = strict_json(raw)
            if channel == "agent" and request.get("action") == "describe":
                if set(request) != {"action"}:
                    raise Refusal("UNEXPECTED_FIELDS")
                return json.dumps({"ok": True, "operation": self.profile.operation(),
                                   "approval_required": True}, ensure_ascii=True, allow_nan=False).encode("ascii")
            if channel == "agent" and request.get("action") != "propose":
                if type(request.get("request_id")) is not str:
                    raise Refusal("UNKNOWN_REQUEST")
                with self.origin_lock:
                    origin = self.origins.get(request.get("request_id"))
                if origin != {"sid": principal.sid, "session_id": principal.session_id}:
                    raise Refusal("WRONG_REQUEST_SESSION")
            if channel == "agent" and request.get("action") == "consume":
                result = dispatch_read(self.ledger, principal.sid, request,
                                       profile=self.profile, start=self.start)
            else:
                result = self.ledger.handle(channel, principal.sid, request)
            if channel == "agent" and request.get("action") == "propose":
                with self.origin_lock:
                    self.origins[result["request_id"]] = {"sid": principal.sid, "session_id": principal.session_id}
                self.pending.put_nowait({k: result[k] for k in ("request_id", "operation_sha256")})
            if channel == "decision" and request.get("action") == "inspect":
                with self.origin_lock:
                    result = {**result, "owner_actor": {"sid": self.owner.sid, "session_id": self.owner.session_id},
                              "request_origin": self.origins.get(result["request_id"]),
                              "session_separation_required": True}
            return json.dumps({"ok": True, **result}, ensure_ascii=True, allow_nan=False).encode("ascii")
        except ReadError as error:
            if error.code in {"YC_READ_CLEANUP_INCOMPLETE", "YC_READ_CONTEXT_CHANGED", "YC_READ_PROVIDER_UNAVAILABLE",
                              "YC_READ_NATIVE_DENY", "YC_READ_OBSERVATION_STALE"}:
                self.stopping.set()
                self.ledger.close()
            return b'{"ok":false,"code":"YC_READ_REFUSED"}'
        except ProjectionError:
            return b'{"ok":false,"code":"YC_READ_REFUSED"}'
        except boundary.BoundaryError:
            return b'{"ok":false,"code":"OWNER_SESSION_BOUNDARY_REFUSED"}'
        except Refusal as error:
            # Ledger exceptions contain fixed codes only; JSON parse causes are never emitted.
            return json.dumps({"ok": False, "code": str(error)}, ensure_ascii=True).encode("ascii")
        except Exception:
            # Unknown trusted provider failures stop the whole host, without leaking their diagnostics.
            self.ledger.close()
            raise ReadError("YC_READ_HOST_FAILED") from None

    def close(self):
        # Grants are cancelled before waiting for transport workers to finish.
        self.stopping.set()
        self.ledger.close()
        self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

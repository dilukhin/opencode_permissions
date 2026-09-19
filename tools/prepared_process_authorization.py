"""Single-process, single-session continuation owner for prepared local calls.

HostPort belongs ONLY to the trusted native approval event handler. ExecutionPort
belongs to the agent-safe bridge. Neither is a JSON/CLI/tool-facing interface.
This is not authenticated IPC and does not establish an OpenCode host bridge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Callable

from prepared_process_adapter import (
    Projection, TRANSPORT, classify_prepared, project_prepared, text,
)


class AuthorizationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CallBinding:
    session_id: str
    call_id: str
    source_txn_id: str
    attempt_txn_id: str
    role: str
    transport: str = TRANSPORT


class _Ticket:
    __slots__ = ()


@dataclass(frozen=True, repr=False)
class PendingCall:
    decision: str
    projection: Projection
    continuation: object | None


@dataclass
class _Entry:
    binding: CallBinding
    projection: Projection
    deadline: float
    state: str = "PENDING"


class _Session:
    def __init__(self, *, session_id: str, platform: str,
                 acquire: Callable[[CallBinding], object],
                 native_check: Callable[[CallBinding, Projection], str],
                 ttl_seconds: int, capacity: int, clock: Callable[[], float]):
        text(session_id, limit=256)
        if platform not in {"linux", "windows"}:
            raise AuthorizationError("PLATFORM_UNSUPPORTED")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise AuthorizationError("TTL_INVALID")
        if type(capacity) is not int or not 1 <= capacity <= 10000:
            raise AuthorizationError("CAPACITY_INVALID")
        if not callable(acquire) or not callable(native_check) or not callable(clock):
            raise AuthorizationError("TRUSTED_PROVIDER_REQUIRED")
        self.session_id, self.platform = session_id, platform
        self.acquire, self.native_check = acquire, native_check
        self.ttl, self.capacity, self.clock = ttl_seconds, capacity, clock
        self.entries: dict[object, _Entry] = {}
        self.sources: set[CallBinding] = set()
        self.closed = False
        self.lock = threading.Lock()

    def _binding(self, binding: CallBinding) -> None:
        if type(binding) is not CallBinding:
            raise AuthorizationError("CALL_BINDING_INVALID")
        for value in (binding.session_id, binding.call_id, binding.source_txn_id, binding.attempt_txn_id):
            text(value, limit=256)
        if binding.session_id != self.session_id or binding.transport != TRANSPORT:
            raise AuthorizationError("SESSION_OR_TRANSPORT_MISMATCH")
        if binding.role not in {"process", "verify"}:
            raise AuthorizationError("ROLE_INVALID")

    def _observe(self, binding: CallBinding) -> tuple[Projection, dict]:
        try:
            projection = project_prepared(self.acquire(binding), platform=self.platform)
            if (projection.source_txn_id, projection.attempt_txn_id, projection.role) != (
                    binding.source_txn_id, binding.attempt_txn_id, binding.role):
                raise AuthorizationError("PREPARED_BINDING_MISMATCH")
            decision = classify_prepared(projection, native_decision=self.native_check(binding, projection))
            return projection, decision
        except AuthorizationError:
            raise
        except Exception:
            # Do not leak argv/stdin/path or provider exception content.
            raise AuthorizationError("ACQUISITION_OR_POLICY_FAILED") from None

    def _live(self) -> None:
        if self.closed:
            raise AuthorizationError("SESSION_CLOSED")

    def _entry(self, ticket: object, binding: CallBinding) -> _Entry:
        self._live()
        if type(ticket) is not _Ticket or ticket not in self.entries:
            raise AuthorizationError("CONTINUATION_UNKNOWN")
        entry = self.entries[ticket]
        if entry.state in {"CONSUMED", "REVOKED", "EXPIRED"}:
            raise AuthorizationError("CONTINUATION_" + entry.state)
        if self.clock() >= entry.deadline:
            entry.state = "EXPIRED"
            raise AuthorizationError("CONTINUATION_EXPIRED")
        if binding != entry.binding:
            entry.state = "REVOKED"
            raise AuthorizationError("CALL_BINDING_MISMATCH")
        return entry

    def request(self, binding: CallBinding) -> PendingCall:
        with self.lock:
            self._live()
            self._binding(binding)
            if binding in self.sources:
                raise AuthorizationError("CALL_ALREADY_REQUESTED")
            if len(self.sources) >= self.capacity:
                raise AuthorizationError("SESSION_CAPACITY")
            # Reserve before acquisition: a failure cannot silently retry a call.
            self.sources.add(binding)
            deadline = self.clock() + self.ttl
            projection, result = self._observe(binding)
            if result["decision"] == "DENY":
                return PendingCall("DENY", projection, None)
            if self.clock() >= deadline:
                raise AuthorizationError("CONTINUATION_EXPIRED")
            ticket = _Ticket()
            self.entries[ticket] = _Entry(binding, projection, deadline)
            return PendingCall("ASK_USER", projection, ticket)

    def approve_once(self, ticket: object, binding: CallBinding, *, snapshot_identity: str) -> None:
        with self.lock:
            entry = self._entry(ticket, binding)
            if entry.state != "PENDING":
                raise AuthorizationError("CONTINUATION_NOT_PENDING")
            if snapshot_identity != entry.projection.snapshot_identity:
                entry.state = "REVOKED"
                raise AuthorizationError("APPROVAL_SNAPSHOT_MISMATCH")
            # This method is callable ONLY by HostPort after a native once event.
            # It does not change the classifier's ASK into automatic ALLOW.
            entry.state = "APPROVED_ONCE"

    def consume(self, ticket: object, binding: CallBinding) -> Projection:
        with self.lock:
            entry = self._entry(ticket, binding)
            if entry.state != "APPROVED_ONCE":
                raise AuthorizationError("CONTINUATION_NOT_APPROVED")
            try:
                fresh, result = self._observe(binding)
                if fresh != entry.projection:
                    raise AuthorizationError("PREPARED_DRIFT")
                if result["decision"] == "DENY":
                    raise AuthorizationError("NATIVE_DENY")
                if self.clock() >= entry.deadline:
                    raise AuthorizationError("CONTINUATION_EXPIRED")
            except BaseException:
                entry.state = "REVOKED"
                raise
            entry.state = "CONSUMED"
            return entry.projection

    def cancel(self, ticket: object) -> None:
        with self.lock:
            self._live()
            if type(ticket) is not _Ticket or ticket not in self.entries:
                raise AuthorizationError("CONTINUATION_UNKNOWN")
            entry = self.entries[ticket]
            if entry.state != "CONSUMED":
                entry.state = "REVOKED"

    def close(self) -> None:
        with self.lock:
            self.closed = True
            self.entries.clear()
            self.sources.clear()


@dataclass(frozen=True, repr=False)
class HostPort:
    _session: _Session = field(repr=False)

    def approve_once(self, continuation: object, binding: CallBinding, *, snapshot_identity: str) -> None:
        self._session.approve_once(continuation, binding, snapshot_identity=snapshot_identity)

    def cancel(self, continuation: object) -> None:
        self._session.cancel(continuation)

    def close(self) -> None:
        self._session.close()


@dataclass(frozen=True, repr=False)
class ExecutionPort:
    _session: _Session = field(repr=False)

    def request(self, binding: CallBinding) -> PendingCall:
        return self._session.request(binding)

    def consume(self, continuation: object, binding: CallBinding) -> Projection:
        return self._session.consume(continuation, binding)


def create_local_session(*, session_id: str, platform: str,
                         acquire: Callable[[CallBinding], object],
                         native_check: Callable[[CallBinding, Projection], str],
                         ttl_seconds: int = 60, capacity: int = 1024,
                         clock: Callable[[], float] = time.monotonic) -> tuple[HostPort, ExecutionPort]:
    """Trusted bootstrap only. Never pass these providers or HostPort from tool input.

    acquire must freshly run agent-safe prepare_process and runtime preconditions,
    enforce the non-secret profile, and supply immutable original call context.
    native_check must observe current native policy, not a caller-provided flag.
    No callback executes a subprocess. Providers must not re-enter the session.
    """
    session = _Session(session_id=session_id, platform=platform, acquire=acquire,
        native_check=native_check, ttl_seconds=ttl_seconds, capacity=capacity, clock=clock)
    return HostPort(session), ExecutionPort(session)

"""Испытательный журнал потребления согласия #57, НЕ источник полномочий.

Нет CLI, IPC, OpenCode, SSH, запуска процессов или выдачи рабочего grant.
Защищённый владелец #47 в будущем может использовать такой backend; этот
модуль проверяет только атомарность учёта на искусственных данных.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid


SCHEMA = 1
MAX_ENTRIES = 1024
MAX_TTL_MS = 60_000
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_STATES = frozenset({"pending", "approved", "rejected", "cancelled",
                     "expired", "invalidated", "consumed"})


class Refusal(Exception):
    """Только фиксированный код; ошибки SQLite/пути не передаются вызывающему."""


@dataclass(frozen=True)
class Binding:
    transaction_id: str
    operation_sha256: str
    policy_sha256: str
    deadline_unix_ms: int


def _uuid(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _binding(value):
    if (type(value) is not Binding or not _uuid(value.transaction_id)
            or type(value.operation_sha256) is not str or not _DIGEST.fullmatch(value.operation_sha256)
            or type(value.policy_sha256) is not str or not _DIGEST.fullmatch(value.policy_sha256)
            or type(value.deadline_unix_ms) is not int
            or not 0 <= value.deadline_unix_ms < 2**63):
        raise Refusal("INVALID_BINDING")
    return (value.transaction_id, value.operation_sha256, value.policy_sha256, value.deadline_unix_ms)


class IntentJournal:
    """Хранилище тестового автомата, доступное только будущему trusted owner.

    UUID поколения не является credential. Файлы и API этого fixture доступны
    тестовому процессу; OS-изоляция и реальное согласие здесь НЕ доказаны.
    """

    def __init__(self, path, owner_instance_id, clock=None):
        self.owner_instance_id = owner_instance_id
        self.clock = clock or (lambda: time.time_ns() // 1_000_000)
        self.poisoned = False
        self.db = None
        try:
            # mode=rw не создаёт потерянную БД заново и не стирает tombstones.
            uri = Path(path).absolute().as_uri() + "?mode=rw"
            self.db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            if self.db.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise Refusal("UNSUPPORTED_STORAGE_MODE")
        except (sqlite3.Error, ValueError, OSError, Refusal) as error:
            if self.db is not None:
                self.db.close()
            if isinstance(error, Refusal):
                raise
            raise Refusal("STORAGE_UNAVAILABLE") from None

    @classmethod
    def create(cls, path, *, clock=None):
        """Явное одноразовое создание только испытательной БД; без cleanup."""
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        except OSError:
            raise Refusal("STORE_CREATE_REFUSED") from None
        result = cls(path, str(uuid.uuid4()), clock)
        try:
            result.db.execute("BEGIN IMMEDIATE")
            result.db.execute("CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), "
                              "schema_version INTEGER NOT NULL, epoch TEXT NOT NULL, last_clock INTEGER NOT NULL)")
            result.db.execute("CREATE TABLE intents (transaction_id TEXT PRIMARY KEY, "
                              "operation_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL, "
                              "deadline INTEGER NOT NULL, epoch TEXT NOT NULL, state TEXT NOT NULL "
                              "CHECK(state IN ('pending','approved','rejected','cancelled','expired','invalidated','consumed')))")
            result.db.execute("CREATE TABLE audit (seq INTEGER PRIMARY KEY, "
                              "transaction_id TEXT NOT NULL REFERENCES intents(transaction_id), "
                              "state TEXT NOT NULL, epoch TEXT NOT NULL, at_ms INTEGER NOT NULL)")
            now = result._now()
            result.db.execute("INSERT INTO metadata VALUES (1,?,?,?)", (SCHEMA, result.owner_instance_id, now))
            result._commit()
        except (sqlite3.Error, Refusal):
            result.close()
            # При неясном создании сохраняется файл, а не запускается repair.
            raise Refusal("STORE_INITIALIZATION_FAILED") from None
        return result

    @classmethod
    def attach(cls, path, owner_instance_id, *, clock=None):
        """Второе соединение того же тестового владельца, не новый owner."""
        if not _uuid(owner_instance_id):
            raise Refusal("INVALID_OWNER_EPOCH")
        result = cls(path, owner_instance_id, clock)
        try:
            result._metadata()
        except (sqlite3.Error, Refusal):
            result.close()
            raise Refusal("OWNER_OR_STORE_UNAVAILABLE") from None
        return result

    @classmethod
    def restart(cls, path, *, clock=None):
        """Новое поколение владельца: неиспользованные согласия отзываются."""
        result = cls(path, None, clock)
        try:
            result.db.execute("BEGIN IMMEDIATE")
            meta = result._metadata(check_epoch=False)
            now = result._now()
            if now < meta[2]:
                raise Refusal("CLOCK_REGRESSION")
            result.owner_instance_id = str(uuid.uuid4())
            for (transaction_id,) in result.db.execute(
                    "SELECT transaction_id FROM intents WHERE state IN ('pending','approved')").fetchall():
                result._record(transaction_id, "invalidated", now)
            result.db.execute("UPDATE metadata SET epoch=?,last_clock=? WHERE id=1",
                              (result.owner_instance_id, now))
            result._commit()
        except (sqlite3.Error, Refusal):
            result.close()
            raise Refusal("OWNER_RESTART_REFUSED") from None
        return result

    def _now(self):
        try:
            now = self.clock()
        except Exception:
            raise Refusal("CLOCK_UNAVAILABLE") from None
        if type(now) is not int or not 0 <= now < 2**63:
            raise Refusal("INVALID_CLOCK")
        return now

    def _metadata(self, *, check_epoch=True):
        row = self.db.execute("SELECT schema_version,epoch,last_clock FROM metadata WHERE id=1").fetchone()
        if (row is None or row[0] != SCHEMA or not _uuid(row[1])
                or type(row[2]) is not int or row[2] < 0):
            raise Refusal("INVALID_STORE")
        if check_epoch and row[1] != self.owner_instance_id:
            raise Refusal("STALE_OWNER")
        return row

    def _commit(self):
        self.db.execute("COMMIT")

    @contextmanager
    def _transaction(self):
        if self.poisoned or self.db is None:
            raise Refusal("STORE_BLOCKED")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            meta = self._metadata()
            now = self._now()
            if now < meta[2]:
                raise Refusal("CLOCK_REGRESSION")
            self.db.execute("UPDATE metadata SET last_clock=? WHERE id=1", (now,))
            yield now
            self._commit()
        except (sqlite3.Error, Refusal) as error:
            if self.db.in_transaction:
                try:
                    self.db.execute("ROLLBACK")
                except sqlite3.Error:
                    self.poisoned = True
            if isinstance(error, sqlite3.Error):
                self.poisoned = True
                raise Refusal("STORAGE_UNCERTAIN") from None
            raise

    def _record(self, transaction_id, state, now):
        self.db.execute("UPDATE intents SET state=? WHERE transaction_id=?", (state, transaction_id))
        self.db.execute("INSERT INTO audit(transaction_id,state,epoch,at_ms) VALUES (?,?,?,?)",
                        (transaction_id, state, self.owner_instance_id, now))

    def reserve(self, binding):
        values = _binding(binding)
        with self._transaction() as now:
            if not 0 < binding.deadline_unix_ms - now <= MAX_TTL_MS:
                raise Refusal("INVALID_DEADLINE")
            if self.db.execute("SELECT 1 FROM intents WHERE transaction_id=?", (binding.transaction_id,)).fetchone():
                raise Refusal("DUPLICATE_TRANSACTION")
            if self.db.execute("SELECT count(*) FROM intents").fetchone()[0] >= MAX_ENTRIES:
                raise Refusal("STORE_CAPACITY")
            self.db.execute("INSERT INTO intents VALUES (?,?,?,?,?,'pending')", (*values, self.owner_instance_id))
            self._record(binding.transaction_id, "pending", now)

    def _row(self, binding):
        values = _binding(binding)
        row = self.db.execute("SELECT transaction_id,operation_sha256,policy_sha256,deadline,epoch,state "
                              "FROM intents WHERE transaction_id=?", (binding.transaction_id,)).fetchone()
        if row is None:
            raise Refusal("UNKNOWN_TRANSACTION")
        if row[:4] != values:
            raise Refusal("BINDING_CHANGED")
        if row[5] not in _STATES or not _uuid(row[4]):
            raise Refusal("INVALID_STORE")
        return row

    def _transition(self, binding, allowed, target):
        _binding(binding)
        refusal = None
        with self._transaction() as now:
            row = self._row(binding)
            if row[5] in {"pending", "approved"} and now >= row[3]:
                self._record(binding.transaction_id, "expired", now)
                refusal = "EXPIRED"
            elif row[4] != self.owner_instance_id or row[5] not in allowed:
                refusal = "TRANSITION_REFUSED"
            else:
                self._record(binding.transaction_id, target, now)
        if refusal:
            raise Refusal(refusal)

    def record_decision(self, binding, decision):
        # Это сохранение уже принятого trusted owner решения, а не API агента.
        if type(decision) is not str or decision not in ("approve", "reject"):
            raise Refusal("INVALID_DECISION")
        self._transition(binding, {"pending"}, "approved" if decision == "approve" else "rejected")

    def cancel(self, binding):
        self._transition(binding, {"pending", "approved"}, "cancelled")

    def consume(self, binding):
        # Нормальный возврат доказывает только commit учёта, не право SSH/sudo.
        self._transition(binding, {"approved"}, "consumed")

    def inspect(self, binding):
        if self.poisoned or self.db is None:
            raise Refusal("STORE_BLOCKED")
        try:
            self._metadata()
            return self._row(binding)[5]
        except sqlite3.Error:
            raise Refusal("STORAGE_UNAVAILABLE") from None

    def audit_states(self, binding):
        self.inspect(binding)
        try:
            return [row[0] for row in self.db.execute(
                "SELECT state FROM audit WHERE transaction_id=? ORDER BY seq", (binding.transaction_id,))]
        except sqlite3.Error:
            raise Refusal("STORAGE_UNAVAILABLE") from None

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

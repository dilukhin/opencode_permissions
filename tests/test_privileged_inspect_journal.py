"""Устойчивость учёта согласия #57 на временной БД; рабочего допуска нет."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import privileged_inspect_journal_fixture as fixture
from privileged_inspect_journal_fixture import Binding, IntentJournal, Refusal


TESTS = Path(__file__).resolve().parent
NOW = 10_000


def binding(**updates):
    return replace(Binding(
        str(uuid.uuid4()), hashlib.sha256(b"synthetic-intent-no-execution").hexdigest(),
        hashlib.sha256(b"synthetic-policy").hexdigest(), NOW + 30_000,
    ), **updates)


# Запускается только созданный тестом Python-процесс: ни shell, ни SSH, ни sudo.
WORKER = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from privileged_inspect_journal_fixture import Binding, IntentJournal, Refusal
j = IntentJournal.attach(sys.argv[2], sys.argv[3], clock=lambda: 10000)
b = Binding(**json.loads(sys.argv[4]))
try:
    j.consume(b)
except Refusal:
    print('refused', flush=True)
else:
    if sys.argv[5] == 'crash':
        os._exit(17)
    print('consumed', flush=True)
finally:
    j.close()
"""


class DurableInspectJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "consent.sqlite"
        self.now = NOW
        self.store = IntentJournal.create(self.path, clock=lambda: self.now)
        self.handles = [self.store]
        self.operation = binding()
        self.store.reserve(self.operation)

    def tearDown(self):
        for handle in self.handles:
            handle.close()
        self.directory.cleanup()

    def another(self):
        result = IntentJournal.attach(self.path, self.store.owner_instance_id, clock=lambda: self.now)
        self.handles.append(result)
        return result

    def restart(self):
        result = IntentJournal.restart(self.path, clock=lambda: self.now)
        self.handles.append(result)
        return result

    def process(self, mode="normal"):
        return subprocess.Popen(
            [sys.executable, "-c", WORKER, str(TESTS), str(self.path),
             self.store.owner_instance_id, json.dumps(self.operation.__dict__), mode],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )

    def test_consumption_and_audit_visible_before_return(self):
        self.store.record_decision(self.operation, "approve")
        self.store.consume(self.operation)
        observer = self.another()
        self.assertEqual("consumed", observer.inspect(self.operation))
        self.assertEqual(["pending", "approved", "consumed"], observer.audit_states(self.operation))
        with self.assertRaises(Refusal):
            observer.consume(self.operation)

    def test_pending_has_no_consumption(self):
        with self.assertRaisesRegex(Refusal, "TRANSITION_REFUSED"):
            self.store.consume(self.operation)
        self.assertEqual(["pending"], self.store.audit_states(self.operation))

    def test_reject_cancel_and_expiry_are_final(self):
        for decision in ("reject", "cancel", "expire"):
            item = binding()
            self.store.reserve(item)
            if decision == "reject":
                self.store.record_decision(item, "reject")
            elif decision == "cancel":
                self.store.record_decision(item, "approve")
                self.store.cancel(item)
            else:
                self.now = item.deadline_unix_ms
            with self.subTest(decision=decision), self.assertRaises(Refusal):
                self.store.consume(item)
            with self.assertRaises(Refusal):
                self.store.record_decision(item, "approve")
            self.assertNotIn("consumed", self.store.audit_states(item))
            self.now = NOW + 30_000 if decision == "expire" else NOW

    def test_binding_drift_cannot_approve_or_consume(self):
        self.store.record_decision(self.operation, "approve")
        for field, value in (
            ("operation_sha256", "a" * 64), ("policy_sha256", "b" * 64),
            ("deadline_unix_ms", self.operation.deadline_unix_ms - 1),
            ("transaction_id", str(uuid.uuid4())),
        ):
            changed = replace(self.operation, **{field: value})
            with self.subTest(field=field), self.assertRaises(Refusal):
                self.store.consume(changed)
        self.assertEqual("approved", self.store.inspect(self.operation))
        self.assertEqual(["pending", "approved"], self.store.audit_states(self.operation))

    def test_duplicate_transaction_cannot_get_new_request_even_after_consumption(self):
        for state in ("pending", "approved", "consumed"):
            if state == "approved":
                self.store.record_decision(self.operation, "approve")
            elif state == "consumed":
                self.store.consume(self.operation)
            for candidate in (self.operation, replace(self.operation, operation_sha256="a" * 64)):
                with self.subTest(state=state), self.assertRaisesRegex(Refusal, "DUPLICATE_TRANSACTION"):
                    self.store.reserve(candidate)

    def test_restart_invalidates_unused_consent_and_stale_handles(self):
        pending = binding()
        self.store.reserve(pending)
        self.store.record_decision(self.operation, "approve")
        stale = self.another()
        restarted = self.restart()
        for item in (self.operation, pending):
            self.assertEqual("invalidated", restarted.inspect(item))
            self.assertEqual("invalidated", restarted.audit_states(item)[-1])
            with self.assertRaises(Refusal):
                restarted.consume(item)
            with self.assertRaises(Refusal):
                restarted.reserve(item)
        with self.assertRaisesRegex(Refusal, "STALE_OWNER"):
            stale.consume(self.operation)
        with self.assertRaises(Refusal):
            IntentJournal.attach(self.path, self.store.owner_instance_id)

    def test_consumed_tombstone_survives_restart_and_reopen(self):
        self.store.record_decision(self.operation, "approve")
        self.store.consume(self.operation)
        self.store.close()
        restarted = self.restart()
        self.assertEqual("consumed", restarted.inspect(self.operation))
        with self.assertRaises(Refusal):
            restarted.consume(self.operation)
        with self.assertRaises(Refusal):
            restarted.reserve(self.operation)

    def test_threads_on_separate_connections_have_one_winner(self):
        self.store.record_decision(self.operation, "approve")

        def consume(_):
            handle = IntentJournal.attach(self.path, self.store.owner_instance_id, clock=lambda: NOW)
            try:
                handle.consume(self.operation)
                return "consumed"
            except Refusal:
                return "refused"
            finally:
                handle.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(consume, range(16)))
        self.assertEqual(1, outcomes.count("consumed"))
        self.assertEqual(1, self.store.audit_states(self.operation).count("consumed"))

    def test_processes_have_one_winner(self):
        self.store.record_decision(self.operation, "approve")
        processes = [self.process() for _ in range(6)]
        outcomes = []
        try:
            for process in processes:
                out, err = process.communicate(timeout=15)
                self.assertEqual(0, process.returncode, err)
                outcomes.append(out.strip())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)
        self.assertEqual(1, outcomes.count("consumed"))
        self.assertEqual(5, outcomes.count("refused"))

    def test_abrupt_exit_after_commit_does_not_allow_retry(self):
        self.store.record_decision(self.operation, "approve")
        process = self.process("crash")
        out, _err = process.communicate(timeout=15)
        self.assertEqual(17, process.returncode)
        self.assertEqual("", out)
        self.assertEqual("consumed", self.store.inspect(self.operation))
        restarted = self.restart()
        with self.assertRaises(Refusal):
            restarted.consume(self.operation)

    def test_lost_commit_reply_is_not_retried_and_remains_consumed(self):
        self.store.record_decision(self.operation, "approve")
        real_commit = self.store._commit

        def lose_reply():
            real_commit()
            raise sqlite3.OperationalError("synthetic-private-marker")

        with patch.object(self.store, "_commit", side_effect=lose_reply):
            with self.assertRaisesRegex(Refusal, "STORAGE_UNCERTAIN") as error:
                self.store.consume(self.operation)
        self.assertNotIn("synthetic-private-marker", str(error.exception))
        with self.assertRaisesRegex(Refusal, "STORE_BLOCKED"):
            self.store.consume(self.operation)
        observer = self.another()
        self.assertEqual("consumed", observer.inspect(self.operation))
        with self.assertRaises(Refusal):
            observer.consume(self.operation)

    def test_failed_audit_insert_rolls_back_consumption_and_blocks_handle(self):
        self.store.record_decision(self.operation, "approve")
        self.store.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit "
                              "BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaisesRegex(Refusal, "STORAGE_UNCERTAIN"):
            self.store.consume(self.operation)
        self.assertTrue(self.store.poisoned)
        observer = self.another()
        self.assertEqual("approved", observer.inspect(self.operation))
        self.assertNotIn("consumed", observer.audit_states(self.operation))
        # Не ремонтируем БД для повторной попытки: restart тоже отказывает.
        with self.assertRaises(Refusal):
            self.restart()

    def test_deadline_is_checked_again_before_decision_and_consumption(self):
        self.store.record_decision(self.operation, "approve")
        self.now = self.operation.deadline_unix_ms
        with self.assertRaisesRegex(Refusal, "EXPIRED"):
            self.store.consume(self.operation)
        self.assertEqual("expired", self.store.inspect(self.operation))
        self.assertEqual("expired", self.store.audit_states(self.operation)[-1])

    def test_clock_regression_blocks_decision_and_restart(self):
        self.now -= 1
        with self.assertRaisesRegex(Refusal, "CLOCK_REGRESSION"):
            self.store.record_decision(self.operation, "approve")
        with self.assertRaisesRegex(Refusal, "OWNER_RESTART_REFUSED"):
            self.restart()
        self.assertEqual("pending", self.store.inspect(self.operation))

    def test_invalid_binding_deadline_and_approval_flags_fail_closed(self):
        for field, value in (("transaction_id", "bad"), ("operation_sha256", "a" * 63),
                             ("policy_sha256", None), ("deadline_unix_ms", True),
                             ("deadline_unix_ms", -1), ("deadline_unix_ms", 2**63)):
            with self.subTest(field=field), self.assertRaises(Refusal):
                self.store.reserve(replace(binding(), **{field: value}))
        for deadline in (NOW, NOW - 1, NOW + fixture.MAX_TTL_MS + 1):
            with self.assertRaisesRegex(Refusal, "INVALID_DEADLINE"):
                self.store.reserve(binding(deadline_unix_ms=deadline))
        for decision in (True, False, None, "approved", "native-once", "--approved"):
            with self.subTest(decision=decision), self.assertRaises(Refusal):
                self.store.record_decision(self.operation, decision)

    def test_missing_corrupt_existing_and_wrong_schema_stores_are_not_recreated(self):
        missing = self.path.with_name("missing.sqlite")
        with self.assertRaises(Refusal):
            IntentJournal.restart(missing)
        self.assertFalse(missing.exists())
        with self.assertRaises(Refusal):
            IntentJournal.create(self.path)
        corrupt = self.path.with_name("corrupt.sqlite")
        corrupt.write_bytes(b"fixture-corruption")
        before = corrupt.read_bytes()
        with self.assertRaises(Refusal):
            IntentJournal.restart(corrupt)
        self.assertEqual(before, corrupt.read_bytes())
        self.store.db.execute("UPDATE metadata SET schema_version=999")
        with self.assertRaises(Refusal):
            self.restart()

    def test_quota_never_removes_consumed_evidence(self):
        self.store.record_decision(self.operation, "approve")
        self.store.consume(self.operation)
        with patch.object(fixture, "MAX_ENTRIES", 1):
            with self.assertRaisesRegex(Refusal, "STORE_CAPACITY"):
                self.store.reserve(binding())
        self.assertEqual("consumed", self.store.inspect(self.operation))

    def test_store_contains_only_correlation_not_raw_intent_or_permission(self):
        self.store.record_decision(self.operation, "approve")
        self.store.consume(self.operation)
        dump = "\n".join(self.store.db.iterdump())
        self.assertNotIn("synthetic-intent-no-execution", dump)
        for secret in ("raw_stdout", "remote_host_key", "credential", "grant_token", "argv"):
            self.assertNotIn(secret, dump)


if __name__ == "__main__":
    unittest.main()

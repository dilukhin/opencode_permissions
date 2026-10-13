"""Fail-closed checks of the Q1 observer, not a mock of OpenCode permissions."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("q1", Path(__file__).parent / "compatibility" / "run_question_probe.py")
q1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q1)


class QuestionProbeTests(unittest.TestCase):
    def fixture(self):
        req = {"id": "que_fixture", "sessionID": "ses_fixture", "questions": q1.QUESTIONS,
               "tool": {"callID": "call_q1_0", "messageID": "msg_fixture"}}
        part = {"type": "tool", "tool": "question", "sessionID": "ses_fixture", "messageID": "msg_fixture",
                "callID": "call_q1_0", "state": {"status": "completed", "input": {"questions": q1.QUESTIONS},
                "metadata": {"answers": q1.ANSWERS}}}
        events = [{"type": "question.asked", "properties": req}, {"type": "question.replied", "properties": {
            "sessionID": "ses_fixture", "requestID": "que_fixture", "answers": q1.ANSWERS}}]
        return req, [{"parts": [part]}], events

    def test_complete_correlated_lifecycle(self):
        _, messages, events = self.fixture()
        metrics = q1.evaluate(events, messages, "ses_fixture", [q1.QUESTIONS], "reply", True)
        self.assertEqual(metrics["question_request_count"], 1)
        self.assertEqual(metrics["question_item_count"], 3)
        self.assertIsNone(metrics["user_interruption_count"])

    def test_loss_is_inconclusive(self):
        _, messages, events = self.fixture()
        for candidate, complete in [(events, False), (events[1:], True), (events[:1], True)]:
            with self.subTest(candidate=candidate, complete=complete):
                with self.assertRaises(q1.Inconclusive):
                    q1.evaluate(candidate, messages, "ses_fixture", [q1.QUESTIONS], "reply", complete)

    def test_known_defect_duplicate_fails(self):
        _, messages, events = self.fixture()
        with self.assertRaises(AssertionError):
            q1.evaluate(events + events[:1], messages, "ses_fixture", [q1.QUESTIONS], "reply", True)

    def test_answers_and_order_are_checked(self):
        _, messages, events = self.fixture()
        events[1]["properties"]["answers"] = list(reversed(q1.ANSWERS))
        with self.assertRaises(AssertionError):
            q1.evaluate(events, messages, "ses_fixture", [q1.QUESTIONS], "reply", True)
        for bad in [[], list(reversed(q1.ANSWERS)), q1.ANSWERS + [["extra"]], "yes"]:
            with self.assertRaises(ValueError):
                q1.guard_answers(bad, q1.ANSWERS)

    def test_request_binding_before_reply(self):
        req, messages, _ = self.fixture()
        messages[0]["parts"][0]["state"]["status"] = "running"
        q1.guard_request(req, "ses_fixture", "call_q1_0", q1.QUESTIONS, messages)
        for field in ["sessionID", "id", "tool", "questions"]:
            bad = copy.deepcopy(req)
            bad[field] = {"callID": "wrong"} if field == "tool" else [] if field == "questions" else "wrong"
            with self.subTest(field=field), self.assertRaises(q1.Inconclusive):
                q1.guard_request(bad, "ses_fixture", "call_q1_0", q1.QUESTIONS, messages)

    def test_persisted_call_cannot_be_substituted(self):
        req, messages, _ = self.fixture()
        messages[0]["parts"][0]["messageID"] = "foreign"
        with self.assertRaises(q1.Inconclusive):
            q1.guard_request(req, "ses_fixture", "call_q1_0", q1.QUESTIONS, messages)

    def test_completed_shell_after_question_is_a_failure(self):
        _, messages, events = self.fixture()
        messages[0]["parts"].append({"type": "tool", "tool": "bash", "state": {"status": "completed"}})
        for outcome in ["deny", "ask", "reply"]:
            with self.subTest(outcome=outcome), self.assertRaises(AssertionError):
                q1.evaluate(events, messages, "ses_fixture", [q1.QUESTIONS], outcome, True)

    def test_rejection_does_not_complete_question(self):
        req, messages, events = self.fixture()
        events[1] = {"type": "question.rejected", "properties": {"sessionID": "ses_fixture", "requestID": req["id"]}}
        with self.assertRaises(AssertionError):
            q1.evaluate(events, messages, "ses_fixture", [q1.QUESTIONS], "reject", True)
        messages[0]["parts"][0]["state"]["status"] = "error"
        q1.evaluate(events, messages, "ses_fixture", [q1.QUESTIONS], "reject", True)

    def test_no_questions_when_choices_are_known(self):
        q1.evaluate([], [], "ses_fixture", [], "none", True)
        _, messages, events = self.fixture()
        with self.assertRaises(AssertionError):
            q1.evaluate(events, messages, "ses_fixture", [], "none", True)

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "runtime" / "yc_guard"))

import classifier_yc  # noqa: E402
import yc_transitional_adapter as runtime  # noqa: E402

TRUSTED = {
    "invoked": "yc",
    "resolved_path": "C:/soft/yc/yc.exe",
    "object_identity": "synthetic:yc.exe",
}


def fact(command, *, parser_status="exact", executable=None):
    argv = command.split()
    return {
        "schema": "parsed-simple/v1",
        "platform": "windows",
        "parser": {"status": parser_status, "profile": "synthetic-yc-v1"},
        "executable": dict(executable or TRUSTED),
        "argv": argv,
        "cwd": {"lexical": "C:/repo", "object_identity": "synthetic:cwd", "follow_mode": "target"},
        "targets": [],
        "redirects": [],
        "stdin": {"kind": "none"},
    }


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def __call__(self, executable_path, argv_tail):
        self.calls.append((executable_path, list(argv_tail)))
        return {"returncode": 0}


class YcTransitionalRuntimeTests(unittest.TestCase):
    def dispatch(self, command, **kwargs):
        executor = RecordingExecutor()
        result = runtime.dispatch(
            fact(command),
            trusted_execution_target=TRUSTED,
            executor=executor,
            **kwargs,
        )
        return result, executor

    def test_exact_reads_execute_via_pinned_path(self):
        for command in (
            "yc compute instance list",
            "yc compute instance get --id epd42hrnss08t2440g90",
            "yc compute disk list",
        ):
            with self.subTest(command=command):
                result, executor = self.dispatch(command)
                self.assertEqual(result["decision"], "ALLOW")
                self.assertTrue(result["execute"])
                self.assertFalse(result["transitional_state_change_without_user_prompt"])
                self.assertEqual(len(executor.calls), 1)
                self.assertEqual(executor.calls[0][0], TRUSTED["resolved_path"])
                self.assertNotEqual(executor.calls[0][0], "yc")

    def test_exact_dilyavm_start_stop_execute_under_transitional_exception(self):
        for action in ("start", "stop"):
            command = f"yc compute instance {action} --id epd42hrnss08t2440g90"
            with self.subTest(action=action):
                result, executor = self.dispatch(command)
                self.assertEqual(result["decision"], "ALLOW")
                self.assertEqual(result["reason_codes"], ["yc.policy.exact_mutation"])
                self.assertTrue(result["transitional_state_change_without_user_prompt"])
                self.assertEqual(len(executor.calls), 1)

    def test_wrong_target_and_unknown_never_reach_executor(self):
        for command in (
            "yc compute instance start --id other",
            "yc compute instance start --name dilyavm",
            "yc compute instance start --id epd42hrnss08t2440g90 --quiet",
            "yc compute instance restart --id epd42hrnss08t2440g90",
            "yc unknown command",
        ):
            with self.subTest(command=command):
                result, executor = self.dispatch(command)
                self.assertEqual(result["decision"], "ASK_USER")
                self.assertFalse(result["execute"])
                self.assertEqual(executor.calls, [])

    def test_hard_deny_never_reaches_executor(self):
        for command in (
            "yc --guard approve request",
            "yc --guard uninstall",
            "yc config list",
            "yc config get token",
            "yc iam key get --id synthetic",
            "yc iam create-token",
            "yc compute instance list --token secret",
        ):
            with self.subTest(command=command):
                result, executor = self.dispatch(command)
                self.assertEqual(result["decision"], "DENY")
                self.assertFalse(result["execute"])
                self.assertEqual(executor.calls, [])

    def test_caller_controlled_approval_is_rejected(self):
        for key in ("approved", "authorized", "policy_allow", "skip_guard", "bypass"):
            with self.subTest(key=key):
                executor = RecordingExecutor()
                with self.assertRaises(runtime.YcRuntimeContractError) as ctx:
                    runtime.dispatch(
                        fact("yc compute instance start --id epd42hrnss08t2440g90"),
                        trusted_execution_target=TRUSTED,
                        executor=executor,
                        caller_context={key: True},
                    )
                self.assertEqual(ctx.exception.code, "CALLER_APPROVAL_NOT_TRUSTED")
                self.assertEqual(executor.calls, [])

    def test_downstream_identity_mismatch_fails_closed(self):
        executor = RecordingExecutor()
        mismatch = dict(TRUSTED)
        mismatch["object_identity"] = "synthetic:other.exe"
        with self.assertRaises(runtime.YcRuntimeContractError) as ctx:
            runtime.dispatch(
                fact("yc compute instance list", executable=mismatch),
                trusted_execution_target=TRUSTED,
                executor=executor,
            )
        self.assertEqual(ctx.exception.code, "DOWNSTREAM_EXECUTABLE_IDENTITY_MISMATCH")
        self.assertEqual(executor.calls, [])

    def test_runtime_decision_matches_canonical_classifier(self):
        for command in (
            "yc compute instance list",
            "yc compute instance start --id epd42hrnss08t2440g90",
            "yc compute instance start --id other",
            "yc iam service-account list",
            "yc iam key get --id synthetic",
        ):
            with self.subTest(command=command):
                canonical = classifier_yc.analyze_yc(fact(command))
                observed = runtime.evaluate(fact(command), trusted_execution_target=TRUSTED)
                self.assertEqual(observed["decision"], canonical["decision"])
                self.assertEqual(observed["operation_identity"], canonical["operation_identity"])
                self.assertEqual(observed["reason_codes"], canonical["reason_codes"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SIM_PATH=ROOT/"tests"/"native_policy"/"native_policy_sim.py"
POLICY_PATH=ROOT/"tests"/"native_policy"/"policy_candidate.json"
PROJECTION_PATH=ROOT/"tests"/"native_policy"/"corpus_projection.json"

spec=importlib.util.spec_from_file_location("native_policy_sim",SIM_PATH)
sim=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(sim)

class NativePolicyMatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.projection=json.loads(PROJECTION_PATH.read_text(encoding="utf-8"))
        cls.rules=sim.expand_rules(cls.policy)

    def test_space_star_matches_base(self):
        self.assertTrue(sim.wildcard_match("git status","git status *"))
        self.assertTrue(sim.wildcard_match("git status --short","git status *"))

    def test_backslash_normalization(self):
        self.assertTrue(sim.wildcard_match(r"src\example.cpp","src/example.cpp"))

    def test_platform_case_behavior(self):
        self.assertTrue(sim.wildcard_match("remove-item x","Remove-Item *","win32"))
        self.assertFalse(sim.wildcard_match("remove-item x","Remove-Item *","posix"))

    def test_redirect_override(self):
        r=sim.evaluate_pattern("bash","git status --short > out.txt",self.rules,"posix")
        self.assertEqual((r["action"],r["rule_id"]),("ask","bash.redirect_out.ask"))

    def test_secret_read_denies(self):
        self.assertEqual(sim.evaluate_pattern("read",".env",self.rules)["action"],"deny")
        self.assertEqual(sim.evaluate_pattern("read","keys/id_rsa.pem",self.rules)["action"],"deny")

    def test_nonsecret_read_allows(self):
        self.assertEqual(sim.evaluate_pattern("read","src/example.cpp",self.rules)["action"],"allow")

    def test_grep_wrapper_unknown_stay_non_allow(self):
        self.assertEqual(sim.evaluate_pattern("grep","TODO",self.rules)["action"],"ask")
        self.assertEqual(sim.evaluate_pattern("bash","safe exec-risky -- echo ok",self.rules)["action"],"ask")
        self.assertEqual(sim.evaluate_pattern("bash","helperctl run -- payload",self.rules)["action"],"ask")

    def test_destructive_wrapper_denies(self):
        self.assertEqual(
            sim.evaluate_pattern("bash","safe exec-risky -- rm -rf build",self.rules)["action"],
            "deny",
        )

    def assert_metrics(self,platform):
        s=sim.summarize(self.policy,self.projection,platform)["summary"]
        self.assertEqual(s["source_total"],69)
        self.assertEqual(s["native_scope"],65)
        self.assertEqual(s["excluded_non_native"],4)
        self.assertEqual(s["candidate_counts"],{"allow":6,"ask":30,"deny":29})
        self.assertEqual(s["unsafe_auto_allow"],0)
        self.assertEqual(s["dangerous_false_safe"],0)
        self.assertEqual(s["wrapper_false_safe"],0)
        self.assertEqual(s["unknown_false_safe"],0)
        self.assertEqual(s["secret_false_safe"],0)
        self.assertEqual(s["expected_deny_but_native_ask"],2)
        self.assertEqual(s["expected_allow_but_native_ask"],5)

    def test_metrics_posix(self):
        self.assert_metrics("posix")

    def test_metrics_win32(self):
        self.assert_metrics("win32")

if __name__=="__main__":
    unittest.main()

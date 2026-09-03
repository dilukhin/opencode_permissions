import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools" / "render_native_policy.py"
SIM = ROOT / "tests" / "native_policy" / "native_policy_sim.py"
CANDIDATE = ROOT / "tests" / "native_policy" / "policy_candidate.json"
PROJECTION = ROOT / "tests" / "native_policy" / "corpus_projection.json"

rspec = importlib.util.spec_from_file_location("render_native_policy", RENDERER)
renderer = importlib.util.module_from_spec(rspec)
assert rspec.loader is not None
rspec.loader.exec_module(renderer)

sspec = importlib.util.spec_from_file_location("native_policy_sim", SIM)
sim = importlib.util.module_from_spec(sspec)
assert sspec.loader is not None
sspec.loader.exec_module(sim)


class GateBNativeRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        cls.projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
        cls.canonical = renderer.promote_candidate(cls.candidate)
        renderer.validate_canonical(cls.canonical)
        cls.rendered = renderer.render_config(cls.canonical)

    def test_promotion_is_rule_preserving_and_drops_design_status(self):
        self.assertEqual(self.canonical["rules"], self.candidate["rules"])
        self.assertEqual(self.canonical["target"], self.candidate["target"])
        self.assertEqual(self.canonical["format"], "native-policy/v1")
        self.assertNotIn("status", self.canonical)

    def test_fail_closed_fallback_is_first(self):
        self.assertEqual(self.canonical["rules"][0][1:], ["*", "*", "ask"])

    def test_renderer_preserves_relative_order_within_each_permission(self):
        expected = {}
        for _, permission, pattern, action in self.canonical["rules"]:
            expected.setdefault(permission, []).append((pattern, action))
        observed = {
            permission: list(patterns.items())
            for permission, patterns in self.rendered["permission"].items()
        }
        self.assertEqual(observed, expected)

    def test_renderer_rejects_duplicate_permission_pattern(self):
        bad = json.loads(json.dumps(self.canonical))
        bad["rules"].append(["dup", "read", "*", "deny"])
        with self.assertRaises(renderer.RenderError) as ctx:
            renderer.validate_canonical(bad)
        self.assertEqual(ctx.exception.code, "DUPLICATE_PERMISSION_PATTERN")

    def test_renderer_rejects_late_wildcard_permission(self):
        bad = json.loads(json.dumps(self.canonical))
        bad["rules"].append(["late", "*", "late-pattern", "deny"])
        with self.assertRaises(renderer.RenderError) as ctx:
            renderer.validate_canonical(bad)
        self.assertEqual(ctx.exception.code, "WILDCARD_PERMISSION_AFTER_SPECIFIC")

    def test_round_trip_corpus_semantics_posix_and_windows(self):
        original_rules = sim.expand_rules(self.canonical)
        rendered_rules = renderer.flatten_rendered(self.rendered)
        cases = sim.expand_cases(self.projection)
        for platform in ("posix", "win32"):
            for case in cases:
                original = sim.evaluate_case(case, original_rules, platform)["action"]
                rendered = sim.evaluate_case(case, rendered_rules, platform)["action"]
                self.assertEqual(
                    rendered,
                    original,
                    f"{platform} semantic drift for {case['id']}",
                )

    def test_promotion_evidence_digests_are_deterministic(self):
        self.assertEqual(
            renderer.sha256_bytes(renderer.canonical_bytes(self.canonical)),
            renderer.sha256_bytes(renderer.canonical_bytes(self.canonical)),
        )
        self.assertEqual(
            renderer.sha256_bytes(renderer.render_bytes(self.canonical)),
            renderer.sha256_bytes(renderer.render_bytes(self.canonical)),
        )


if __name__ == "__main__":
    unittest.main()

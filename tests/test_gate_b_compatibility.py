import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
COMPAT = ROOT / "compatibility"
REGISTRY = COMPAT / "registry.json"
GATE = COMPAT / "compatibility_gate.py"

spec = importlib.util.spec_from_file_location("compatibility_gate", GATE)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


class GateBCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.registry = gate.load_json(REGISTRY)
        self.p18 = gate.select_profile(REGISTRY, "1.18.18")
        self.p26 = gate.select_profile(REGISTRY, "1.18.26")
        self.p29 = gate.select_profile(REGISTRY, "1.18.29")

    def test_exact_profiles_select_without_nearest_fallback(self):
        self.assertEqual(self.p26["opencode_version"], "1.18.26")
        self.assertEqual(self.p29["opencode_version"], "1.18.29")
        self.assertEqual(
            self.p29["upstream"]["commit"],
            "16747470f976aca3d362ad730bcd3fe82ecc2c9a",
        )
        self.assertEqual(self.registry["selection"], "exact_version_only")
        self.assertFalse(self.registry["nearest_version_fallback"])

    def test_current_target_is_explicit_exact_profile(self):
        current = gate.current_target_profile(REGISTRY)
        self.assertEqual(self.registry["current_target"], "1.18.29")
        self.assertEqual(current["profile_id"], self.p29["profile_id"])

    def test_unknown_future_version_fails_closed(self):
        with self.assertRaises(gate.CompatibilityError) as ctx:
            gate.select_profile(REGISTRY, "1.18.30")
        self.assertEqual(ctx.exception.code, "UNVALIDATED_OPENCODE_VERSION")

    def test_runtime_revalidated_baseline_remains_linux_deployable(self):
        self.assertTrue(self.p26["deployable"])
        self.assertEqual(self.p26["overall_status"], "DEPLOYABLE")
        self.assertEqual(self.p26["deployable_platforms"], ["linux"])
        selected = gate.select_profile(
            REGISTRY,
            "1.18.26",
            require_deployable=True,
            platform="linux",
        )
        self.assertEqual(selected["profile_id"], self.p26["profile_id"])

    def test_current_source_equivalent_candidate_fails_closed_for_deployment_until_promoted(self):
        self.assertEqual(self.p29["overall_status"], "SOURCE_EQUIVALENT")
        self.assertFalse(self.p29["deployable"])
        self.assertIn("LINUX_RUNTIME_REVALIDATION_REQUIRED", self.p29["blocking_reasons"])
        with self.assertRaises(gate.CompatibilityError) as ctx:
            gate.select_profile(
                REGISTRY,
                "1.18.29",
                require_deployable=True,
                platform="linux",
            )
        self.assertEqual(ctx.exception.code, "PROFILE_NOT_DEPLOYABLE")

    def test_full_critical_fingerprint_family_is_source_equivalent(self):
        keys = self.registry["critical_fingerprint_keys"]
        self.assertEqual(len(keys), 16)
        result = gate.compare_fingerprint_family(self.p26, self.p29, keys)
        self.assertEqual(result["result"], "SOURCE_EQUIVALENT")
        self.assertEqual(result["changed_fingerprints"], [])
        self.assertEqual(
            result["family_id"],
            "sha256:171d981f8853ca935d982899b15f3933964f8174e1a1d644f820d048fa07536f",
        )
        self.assertEqual(result["family_id"], self.p29["compatibility_family"]["family_id"])

    def test_changed_fingerprint_returns_targeted_reaudit_list(self):
        changed = copy.deepcopy(self.p29)
        changed["critical_fingerprints"]["shell_tool"]["blob"] = "synthetic-changed-blob"
        result = gate.compare_fingerprint_family(
            self.p26,
            changed,
            self.registry["critical_fingerprint_keys"],
        )
        self.assertEqual(result["result"], "TARGETED_REAUDIT_REQUIRED")
        self.assertEqual(result["changed_fingerprints"], ["shell_tool"])
        self.assertIsNone(result["family_id"])

    def test_missing_fingerprint_fails_closed(self):
        missing = copy.deepcopy(self.p29)
        del missing["critical_fingerprints"]["grep_tool"]
        result = gate.compare_fingerprint_family(
            self.p26,
            missing,
            self.registry["critical_fingerprint_keys"],
        )
        self.assertEqual(result["result"], "TARGETED_REAUDIT_REQUIRED")
        self.assertIsNotNone(result["missing_or_invalid"])
        self.assertIn("grep_tool", result["missing_or_invalid"]["missing"])

    def test_legacy_fast_path_remains_compatible(self):
        result = gate.compare_fast_path(
            self.p18,
            self.p26,
            self.registry["fast_path_shared_fingerprints"],
        )
        self.assertEqual(result["result"], "SOURCE_EQUIVALENT_FAST_PATH_ELIGIBLE")

    def test_deployable_selection_requires_platform(self):
        with self.assertRaises(gate.CompatibilityError) as ctx:
            gate.select_profile(REGISTRY, "1.18.26", require_deployable=True)
        self.assertEqual(ctx.exception.code, "DEPLOYABLE_PLATFORM_REQUIRED")

    def test_profiles_do_not_contain_secret_material(self):
        for profile in (self.p18, self.p26, self.p29):
            text = json.dumps(profile).lower()
            for forbidden in ("password", "api_key", "private_key", "authorization_header"):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()

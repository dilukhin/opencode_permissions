import copy
import importlib.util
import json
from pathlib import Path
import tempfile
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

    def test_exact_current_version_selects_exact_profile(self):
        self.assertEqual(self.p26["opencode_version"], "1.18.26")
        self.assertEqual(
            self.p26["upstream"]["commit"],
            "774cc7c1914e4329eefde5a669f938b0cf566661",
        )

    def test_unknown_future_version_fails_closed(self):
        with self.assertRaises(gate.CompatibilityError) as ctx:
            gate.select_profile(REGISTRY, "1.18.27")
        self.assertEqual(ctx.exception.code, "UNVALIDATED_OPENCODE_VERSION")

    def test_registry_forbids_nearest_version_fallback(self):
        self.assertEqual(self.registry["selection"], "exact_version_only")
        self.assertFalse(self.registry["nearest_version_fallback"])

    def test_current_profile_is_not_deployable(self):
        self.assertFalse(self.p26["deployable"])
        self.assertEqual(self.p26.get("deployable_platforms", []), [])
        with self.assertRaises(gate.CompatibilityError) as ctx:
            gate.select_profile(
                REGISTRY,
                "1.18.26",
                require_deployable=True,
                platform="linux",
            )
        self.assertEqual(ctx.exception.code, "PROFILE_NOT_DEPLOYABLE")

    def test_linux_runtime_windows_source_status_with_b_p2_evidence(self):
        self.assertEqual(self.p26["overall_status"], "SOURCE_REVALIDATED")
        self.assertEqual(self.p26["platform_status"]["linux"], "RUNTIME_REVALIDATED")
        self.assertEqual(self.p26["platform_status"]["windows"], "SOURCE_REVALIDATED")
        win = self.p26["runtime_observation"]["windows"]
        self.assertEqual(win["result"], "B-P2_PASS")
        self.assertFalse(win["opencode_runtime_executed"])
        self.assertEqual(win["evidence"], "docs/gate_b_windows_peer_identity_probe_ru.md")
        self.assertNotIn("WINDOWS_B_P2_PENDING", self.p26["blocking_reasons"])

    def test_deployable_selection_is_platform_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "profiles").mkdir()
            synthetic = copy.deepcopy(self.p26)
            synthetic["deployable"] = True
            synthetic["deployable_platforms"] = ["linux"]
            (td / "profiles" / "p.json").write_text(json.dumps(synthetic), encoding="utf-8")
            registry = {
                "profiles": {"1.18.26": "profiles/p.json"},
                "unknown_version_result": "UNVALIDATED_OPENCODE_VERSION",
                "not_deployable_result": "PROFILE_NOT_DEPLOYABLE",
            }
            (td / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

            with self.assertRaises(gate.CompatibilityError) as ctx:
                gate.select_profile(td / "registry.json", "1.18.26", require_deployable=True)
            self.assertEqual(ctx.exception.code, "DEPLOYABLE_PLATFORM_REQUIRED")

            selected = gate.select_profile(
                td / "registry.json",
                "1.18.26",
                require_deployable=True,
                platform="linux",
            )
            self.assertEqual(selected["opencode_version"], "1.18.26")

            with self.assertRaises(gate.CompatibilityError) as ctx:
                gate.select_profile(
                    td / "registry.json",
                    "1.18.26",
                    require_deployable=True,
                    platform="windows",
                )
            self.assertEqual(ctx.exception.code, "PROFILE_NOT_DEPLOYABLE_FOR_PLATFORM")

    def test_shared_critical_fingerprints_are_identical(self):
        result = gate.compare_fast_path(
            self.p18,
            self.p26,
            self.registry["fast_path_shared_fingerprints"],
        )
        self.assertEqual(result["result"], "SOURCE_EQUIVALENT_FAST_PATH_ELIGIBLE")
        self.assertEqual(result["changed_fingerprints"], [])

    def test_changed_critical_fingerprint_requires_targeted_reaudit(self):
        changed = copy.deepcopy(self.p26)
        changed["critical_fingerprints"]["permission_service"]["blob"] = "synthetic-changed-blob"
        result = gate.compare_fast_path(
            self.p18,
            changed,
            self.registry["fast_path_shared_fingerprints"],
        )
        self.assertEqual(result["result"], "TARGETED_REAUDIT_REQUIRED")
        self.assertEqual(result["changed_fingerprints"], ["permission_service"])

    def test_profiles_do_not_contain_artifact_or_secret_material(self):
        for profile in (self.p18, self.p26):
            self.assertIsNone(profile["policy_artifact_id"])
            text = json.dumps(profile).lower()
            for forbidden in ("password", "api_key", "private_key", "authorization_header"):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "compatibility"))

import run_yc59_native_1_19_5_probe as probe  # noqa: E402


class Yc59NativeObservationTests(unittest.TestCase):
    def test_unknown_or_different_version_never_starts_scenario(self):
        for version in ("", "1.19.0", "1.18.32", "1.19.5-dev", "2.0.23", "1.19.5\nother"):
            with self.subTest(version=version):
                calls = []
                with self.assertRaisesRegex(ValueError, "YC59_NATIVE_EXACT_VERSION_REQUIRED"):
                    probe.observe("synthetic-opencode", "synthetic-shell", version_probe=lambda _path: version,
                                  scenario_runner=lambda *args: calls.append(args))
                self.assertEqual(calls, [])

    def test_fixture_success_never_claims_human_or_installed_yc_authority(self):
        calls = []

        def run(binary, shell, name):
            calls.append((binary, shell, name))
            return {"scenario": name, "status": "PASS"}

        result = probe.observe("synthetic-opencode", "synthetic-shell",
                               version_probe=lambda _path: "1.19.5", scenario_runner=run)
        self.assertEqual([row[2] for row in calls], list(probe.SCENARIOS))
        self.assertEqual(result["reply_origin"], "automated_http_fixture")
        for key in ("human_consent_proven", "installed_dima_hp_binary_proven",
                    "yc_authorization_binding_proven", "deployment_authorized"):
            self.assertIs(result[key], False)
        self.assertEqual(result["cloud_invocations"], 0)
        self.assertEqual(result["result"], "NATIVE_OBSERVED_HUMAN_CONSENT_NOT_PROVEN")

    def test_failed_scenario_is_not_observation_success(self):
        with self.assertRaisesRegex(ValueError, "YC59_NATIVE_SCENARIO_FAILED"):
            probe.observe("synthetic-opencode", "synthetic-shell", version_probe=lambda _path: "1.19.5",
                          scenario_runner=lambda *_args: {"status": "FAIL"})

    def test_observation_pins_do_not_enable_compatibility_profile(self):
        compat = ROOT / "tests" / "compatibility"
        pins = json.loads((compat / "yc59_native_1_19_5_pins.json").read_text(encoding="utf-8"))
        self.assertEqual(pins["opencode_version"], "1.19.5")
        self.assertFalse(pins["deployment_authorized"])
        self.assertRegex(pins["upstream_commit"], r"^[0-9a-f]{40}$")
        for asset in pins["assets"].values():
            self.assertRegex(asset["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(asset["size"], 0)
        registry = json.loads((compat / "registry.json").read_text(encoding="utf-8"))
        self.assertNotIn("1.19.5", registry["profiles"])
        self.assertFalse(registry["nearest_version_fallback"])


if __name__ == "__main__":
    unittest.main()

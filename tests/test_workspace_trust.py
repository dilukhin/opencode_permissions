import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "workspace_trust.py"
spec = importlib.util.spec_from_file_location("workspace_trust", MODULE)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)


LINUX_WORKSPACE = {
    "platform": "linux",
    "requested_root": "/home/user/projects/example",
    "resolved_root": "/home/user/projects/example",
    "object_identity": "linux:dev=1:ino=42",
}

WINDOWS_WORKSPACE = {
    "platform": "windows",
    "requested_root": r"C:\Users\user\Projects\example",
    "resolved_root": r"C:\Users\user\Projects\example",
    "object_identity": "windows:volume=V:file=F",
}


def fact(workspace=None, scopes=None):
    return {
        "schema": "workspace-trust-fact/v1",
        "trust_class": "development",
        "workspace": dict(workspace or LINUX_WORKSPACE),
        "scopes": list(scopes or ["build", "test"]),
    }


class WorkspaceTrustTests(unittest.TestCase):
    def assert_code(self, code, value):
        with self.assertRaises(m.WorkspaceTrustError) as ctx:
            m.validate_workspace_trust_fact(value)
        self.assertEqual(ctx.exception.code, code)

    def test_valid_fact_normalizes_scope_order(self):
        value = fact(scopes=["test", "build"])
        validated = m.validate_workspace_trust_fact(value)
        self.assertEqual(validated["scopes"], ["build", "test"])

    def test_windows_absolute_identity_is_supported_without_case_folding(self):
        value = fact(WINDOWS_WORKSPACE, ["static_check"])
        self.assertEqual(m.validate_workspace_trust_fact(value)["workspace"], WINDOWS_WORKSPACE)
        changed = dict(WINDOWS_WORKSPACE)
        changed["requested_root"] = r"c:\Users\user\Projects\example"
        self.assertFalse(m.match_workspace_trust_fact(value, changed)["matched"])

    def test_unknown_schema_rejected(self):
        value = fact()
        value["schema"] = "workspace-trust-fact/v2"
        self.assert_code("fact.schema_unsupported", value)

    def test_unknown_trust_class_rejected(self):
        value = fact()
        value["trust_class"] = "all"
        self.assert_code("fact.trust_class_unsupported", value)

    def test_empty_scopes_rejected(self):
        value = fact()
        value["scopes"] = []
        self.assert_code("fact.scopes_invalid", value)

    def test_duplicate_scope_rejected(self):
        self.assert_code("fact.scopes_duplicate", fact(scopes=["build", "build"]))

    def test_unknown_or_wildcard_scope_rejected(self):
        for scope in ["all", "shell", "delete", "*"]:
            with self.subTest(scope=scope):
                self.assert_code("fact.scope_unsupported", fact(scopes=[scope]))

    def test_extra_caller_controlled_trusted_flag_rejected(self):
        value = fact()
        value["trusted"] = True
        self.assert_code("fact.invalid_shape", value)

    def test_relative_roots_rejected(self):
        for field in ["requested_root", "resolved_root"]:
            with self.subTest(field=field):
                workspace = dict(LINUX_WORKSPACE)
                workspace[field] = "projects/example"
                self.assert_code(f"workspace.{field}_invalid", fact(workspace))

    def test_exact_match_returns_only_declared_scopes(self):
        result = m.match_workspace_trust_fact(fact(scopes=["test", "build"]), LINUX_WORKSPACE)
        self.assertEqual(
            result,
            {"matched": True, "scopes": ["build", "test"], "reason": "workspace.exact_match"},
        )

    def test_platform_substitution_fails_closed(self):
        observed = dict(LINUX_WORKSPACE)
        observed["platform"] = "windows"
        self.assertFalse(m.match_workspace_trust_fact(fact(), observed)["matched"])

    def test_requested_root_substitution_fails_closed(self):
        observed = dict(LINUX_WORKSPACE)
        observed["requested_root"] = "/home/user/projects/other"
        self.assertEqual(
            m.match_workspace_trust_fact(fact(), observed)["reason"],
            "workspace.requested_root_mismatch",
        )

    def test_resolved_root_substitution_fails_closed(self):
        observed = dict(LINUX_WORKSPACE)
        observed["resolved_root"] = "/srv/other"
        self.assertEqual(
            m.match_workspace_trust_fact(fact(), observed)["reason"],
            "workspace.resolved_root_mismatch",
        )

    def test_object_identity_substitution_fails_closed(self):
        observed = dict(LINUX_WORKSPACE)
        observed["object_identity"] = "linux:dev=1:ino=99"
        self.assertEqual(
            m.match_workspace_trust_fact(fact(), observed)["reason"],
            "workspace.object_identity_mismatch",
        )

    def test_incomplete_observed_workspace_fails_closed(self):
        observed = dict(LINUX_WORKSPACE)
        del observed["object_identity"]
        result = m.match_workspace_trust_fact(fact(), observed)
        self.assertFalse(result["matched"])
        self.assertEqual(result["scopes"], [])

    def test_validator_does_not_establish_provider_authenticity(self):
        # A syntactically valid JSON fact can still be forged. The pure matcher
        # deliberately has no API that claims provider authenticity.
        validated = m.validate_workspace_trust_fact(fact())
        self.assertNotIn("authenticated", validated)
        self.assertNotIn("trusted_provider", validated)


if __name__ == "__main__":
    unittest.main()

import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "normalized_operation_identity.py"
FIXTURES = ROOT / "tests" / "normalized_operation" / "identity_relations.json"

spec = importlib.util.spec_from_file_location("normalized_operation_identity", MODULE)
identity = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(identity)


def pointer_tokens(path):
    if path == "":
        return []
    assert path.startswith("/")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def get_at(root, path):
    current = root
    for token in pointer_tokens(path):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def set_at(root, path, value):
    tokens = pointer_tokens(path)
    if not tokens:
        raise AssertionError("fixture must not replace document root")
    current = root
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    last = tokens[-1]
    if isinstance(current, list):
        current[int(last)] = copy.deepcopy(value)
    else:
        current[last] = copy.deepcopy(value)


def delete_at(root, path):
    tokens = pointer_tokens(path)
    current = root
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    last = tokens[-1]
    if isinstance(current, list):
        del current[int(last)]
    else:
        del current[last]


def apply_mutation(base, mutation):
    result = copy.deepcopy(base)
    kind = mutation["kind"]

    if kind == "reorder_object_keys":
        return {key: result[key] for key in reversed(list(result.keys()))}
    if kind == "reorder_semantic_set":
        value = get_at(result, mutation["path"])
        set_at(result, mutation["path"], list(reversed(value)))
        return result
    if kind == "change_excluded_metadata":
        for field in mutation["fields"]:
            result[field] = f"synthetic:{field}"
        return result
    if kind == "set":
        set_at(result, mutation["path"], mutation["value"])
        return result
    if kind == "set_many":
        for path, value in mutation["values"].items():
            set_at(result, path, value)
        return result
    if kind == "merge":
        target = get_at(result, mutation["path"])
        if not isinstance(target, dict):
            raise AssertionError(f"merge target is not object: {mutation['path']}")
        target.update(copy.deepcopy(mutation["value"]))
        return result
    if kind == "replace_windows_separators":
        for path in mutation["paths"]:
            value = get_at(result, path)
            set_at(result, path, value.replace("/", "\\"))
        return result
    if kind == "append":
        target = get_at(result, mutation["path"])
        if not isinstance(target, list):
            raise AssertionError(f"append target is not list: {mutation['path']}")
        target.append(copy.deepcopy(mutation["value"]))
        return result
    if kind in {"remove", "delete"}:
        delete_at(result, mutation["path"])
        return result

    raise AssertionError(f"unsupported fixture mutation kind: {kind}")


class NormalizedOperationIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = identity.load_json_strict(FIXTURES)

    def assert_identity_error(self, code, fn):
        with self.assertRaises(identity.IdentityError) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code)

    def test_jcs_object_order(self):
        self.assertEqual(identity.jcs_dumps({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_jcs_utf16_property_order(self):
        # UTF-16 code-unit order differs from Python code-point order here.
        self.assertEqual(identity.jcs_dumps({"\ue000": 2, "😀": 1}), '{"😀":1,"\ue000":2}')

    def test_jcs_string_escaping(self):
        value = {"x": "\b\t\n\f\r\u0000\\\""}
        self.assertEqual(
            identity.jcs_dumps(value),
            '{"x":"\\b\\t\\n\\f\\r\\u0000\\\\\\\""}',
        )

    def test_strict_loader_rejects_duplicate_keys(self):
        self.assert_identity_error(
            "DUPLICATE_OBJECT_KEY",
            lambda: identity.strict_loads('{"a":1,"a":2}'),
        )

    def test_float_and_nonfinite_values_are_rejected(self):
        self.assert_identity_error("FLOAT_NOT_ALLOWED", lambda: identity.jcs_dumps(1.25))
        self.assert_identity_error("FLOAT_NOT_ALLOWED", lambda: identity.strict_loads("1.25"))
        self.assert_identity_error(
            "NON_FINITE_NUMBER_NOT_ALLOWED",
            lambda: identity.strict_loads("NaN"),
        )

    def test_unsafe_integer_is_rejected(self):
        self.assert_identity_error(
            "INTEGER_OUTSIDE_IJSON_SAFE_RANGE",
            lambda: identity.jcs_dumps(identity.MAX_SAFE_INTEGER + 1),
        )

    def test_unpaired_surrogate_is_rejected(self):
        self.assert_identity_error(
            "INVALID_UNICODE_SURROGATE",
            lambda: identity.jcs_dumps("\ud800"),
        )

    def test_known_base_identity_vector(self):
        operation = self.fixture["base_operations"]["local_git_status"]
        self.assertEqual(
            identity.operation_identity(operation),
            "sha256:1ebea4115e8cb42678a058e892edafaf444de06caa1c7ce5c93f530181068040",
        )

    def test_excluded_metadata_does_not_change_identity(self):
        operation = copy.deepcopy(self.fixture["base_operations"]["local_git_status"])
        changed = copy.deepcopy(operation)
        changed.update(
            {
                "purpose": "different prose",
                "display": {"label": "different"},
                "operation_id": "correlation-only",
            }
        )
        self.assertEqual(identity.identity_relation(operation, changed), "SAME")

    def test_unknown_top_level_field_fails_closed(self):
        operation = copy.deepcopy(self.fixture["base_operations"]["local_git_status"])
        operation["mystery_semantics"] = "unknown"
        self.assert_identity_error(
            "UNKNOWN_TOP_LEVEL_FIELD",
            lambda: identity.operation_identity(operation),
        )

    def test_sensitive_context_dependency_is_rejected(self):
        operation = copy.deepcopy(self.fixture["base_operations"]["local_git_status"])
        operation["context_dependencies"] = [
            {"kind": "resolved_variable", "name": "TOKEN", "sensitive": True}
        ]
        self.assert_identity_error(
            "SENSITIVE_CONTEXT_DEPENDENCY_FORBIDDEN",
            lambda: identity.operation_identity(operation),
        )

    def test_schema_or_canonicalization_change_is_non_comparable(self):
        base = copy.deepcopy(self.fixture["base_operations"]["local_git_status"])
        changed_schema = copy.deepcopy(base)
        changed_schema["schema"] = "normalized-operation/v2"
        changed_canon = copy.deepcopy(base)
        changed_canon["canonicalization"] = "op-jcs-v2"
        self.assertEqual(identity.identity_relation(base, changed_schema), "NON_COMPARABLE")
        self.assertEqual(identity.identity_relation(base, changed_canon), "NON_COMPARABLE")

    def test_all_declared_relation_fixtures(self):
        self.assertEqual(self.fixture["case_count"], len(self.fixture["cases"]))
        for case in self.fixture["cases"]:
            with self.subTest(case=case["id"]):
                base = copy.deepcopy(self.fixture["base_operations"][case["base"]])
                mutated = apply_mutation(base, case["mutation"])
                observed = identity.identity_relation(base, mutated)
                self.assertEqual(observed, case["expected_relation"])


if __name__ == "__main__":
    unittest.main()

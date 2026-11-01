"""Synthetic offline tests; no YC process or cloud operation is started."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_yc_transitional_artifact as artifact  # noqa: E402
import classifier_yc  # noqa: E402
import yc_read_projection as projection  # noqa: E402

PRIVATE = "SYNTHETIC_PRIVATE_SENTINEL"
SELECTION = projection.SnapshotSelection("synthetic-folder", "synthetic-vm", "synthetic-disk", "synthetic-snapshot")


def responses():
    return [
        {"id": SELECTION.vm_id, "folderId": SELECTION.folder_id,
         "bootDisk": {"diskId": SELECTION.disk_id},
         "metadata": {"user-data": PRIVATE}, "labels": {"private": PRIVATE},
         "networkInterfaces": [{"primaryV4Address": {"oneToOneNat": {"address": PRIVATE}}}]},
        {"id": SELECTION.disk_id, "folderId": SELECTION.folder_id,
         "size": "9007199254740993", "status": "READY", "typeId": "network-ssd",
         "zoneId": "ru-central1-a", "instanceIds": [SELECTION.vm_id],
         "name": PRIVATE, "description": PRIVATE, "kmsKey": {"keyId": PRIVATE}},
        {"id": SELECTION.snapshot_id, "folderId": SELECTION.folder_id,
         "diskSize": "9007199254740993", "status": "READY", "sourceDiskId": SELECTION.disk_id,
         "createdAt": "2026-11-01T10:00:00.123456789Z", "storageSize": "1024",
         "name": PRIVATE, "description": PRIVATE, "productIds": [PRIVATE]},
    ]


def encode(value):
    return json.dumps(value, ensure_ascii=True).encode("utf-8")


def project(values=None, selection=SELECTION):
    return projection.project_snapshot_context(*(encode(value) for value in (values or responses())), selection=selection)


class YcReadProjectionTests(unittest.TestCase):
    def assert_rejected(self, values, code):
        with self.assertRaises(projection.ProjectionError) as ctx:
            project(values)
        self.assertEqual(str(ctx.exception), code)
        self.assertNotIn(PRIVATE, repr(ctx.exception))
        self.assertIsNone(ctx.exception.__context__)

    def test_exact_projection_preserves_large_integer_and_nanoseconds(self):
        result = project()
        self.assertEqual(result["disk"]["size"], "9007199254740993")
        self.assertEqual(result["snapshot"]["created_at"], "2026-11-01T10:00:00.123456789Z")
        self.assertTrue(result["snapshot_ready"])
        self.assertFalse(result["authorization_granted"])
        self.assertFalse(result["independent_guard_readback"])
        self.assertFalse(result["restore_verified"])
        self.assertEqual(result["vm"], {"id": SELECTION.vm_id, "folder_id": SELECTION.folder_id, "selected_disk_role": "boot"})

    def test_output_field_sets_are_closed_and_private_fields_do_not_escape(self):
        result = project()
        self.assertEqual(set(result), {"schema", "representation", "vm", "disk", "snapshot", "snapshot_ready", "authorization_granted", "independent_guard_readback", "restore_verified"})
        self.assertEqual(set(result["disk"]), {"id", "folder_id", "status", "size", "type_id", "zone_id", "instance_ids"})
        self.assertEqual(set(result["snapshot"]), {"id", "folder_id", "status", "source_disk_id", "disk_size", "created_at"})
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_secondary_disk_selection_is_explicit(self):
        values = responses()
        values[0]["bootDisk"]["diskId"] = "synthetic-other-boot"
        values[0]["secondaryDisks"] = [{"diskId": SELECTION.disk_id}]
        self.assertEqual(project(values)["vm"]["selected_disk_role"], "secondary")

    def test_resource_and_folder_mismatch_never_return_partial_projection(self):
        for index in range(3):
            for field, code in (("id", "YC_PROJECTION_RESOURCE_MISMATCH"), ("folderId", "YC_PROJECTION_FOLDER_MISMATCH")):
                with self.subTest(index=index, field=field):
                    values = responses()
                    values[index][field] = "synthetic-foreign"
                    self.assert_rejected(values, code)

    def test_vm_attachment_and_disk_backreference_must_both_match(self):
        values = responses()
        values[0]["bootDisk"]["diskId"] = "synthetic-other-disk"
        self.assert_rejected(values, "YC_PROJECTION_VM_DISK_MISMATCH")
        for instance_ids in ([], ["synthetic-other-vm"], [SELECTION.vm_id, "synthetic-other-vm"], [SELECTION.vm_id] * 2, SELECTION.vm_id):
            with self.subTest(instance_ids=instance_ids):
                values = responses()
                values[1]["instanceIds"] = instance_ids
                self.assert_rejected(values, "YC_PROJECTION_DISK_VM_MISMATCH")

    def test_duplicate_attachments_and_invalid_attachment_shapes_reject(self):
        for secondary in ([{"diskId": SELECTION.disk_id}], None, "synthetic", [None], [{}], [{"diskId": "synthetic-other"}] * 2,
                          [{"diskId": "synthetic-" + str(i)} for i in range(projection.MAX_ATTACHMENTS + 1)]):
            with self.subTest(secondary=secondary):
                values = responses()
                values[0]["secondaryDisks"] = secondary
                with self.assertRaises(projection.ProjectionError):
                    project(values)

    def test_snapshot_source_is_not_replaced_by_restoration_origin(self):
        values = responses()
        values[2]["sourceDiskId"] = "synthetic-foreign-disk"
        values[1]["sourceSnapshotId"] = SELECTION.snapshot_id
        self.assert_rejected(values, "YC_PROJECTION_SOURCE_DISK_MISMATCH")
        values = responses()
        del values[2]["sourceDiskId"]
        values[2]["sourceSnapshotId"] = SELECTION.disk_id
        self.assert_rejected(values, "YC_PROJECTION_FIELD_MISSING")

    def test_size_changes_require_new_context(self):
        values = responses()
        values[2]["diskSize"] = "1024"
        self.assert_rejected(values, "YC_PROJECTION_SIZE_CONTEXT_CHANGED")

    def test_sizes_are_positive_canonical_int64_strings(self):
        for size in (0, 1, True, None, 1.5, "0", "-1", "+1", "01", "1.0", "1e3", " 1", "1 ", "１", "9223372036854775808", "9" * 100):
            with self.subTest(size=size):
                values = responses()
                values[1]["size"] = values[2]["diskSize"] = size
                code = "YC_PROJECTION_JSON_INVALID" if type(size) is float else "YC_PROJECTION_SIZE_INVALID"
                self.assert_rejected(values, code)
        values = responses()
        values[1]["size"] = values[2]["diskSize"] = "9223372036854775807"
        self.assertEqual(project(values)["disk"]["size"], "9223372036854775807")

    def test_status_is_explicit_and_readiness_is_not_restore_proof(self):
        for disk in ("CREATING", "READY", "ERROR", "DELETING"):
            for snapshot in ("CREATING", "READY", "ERROR", "DELETING"):
                with self.subTest(disk=disk, snapshot=snapshot):
                    values = responses()
                    values[1]["status"], values[2]["status"] = disk, snapshot
                    result = project(values)
                    self.assertEqual(result["snapshot_ready"], disk == snapshot == "READY")
                    self.assertFalse(result["restore_verified"])
        for status in ("ready", "UNKNOWN", "READY\n", 1, True, None, []):
            values = responses()
            values[2]["status"] = status
            self.assert_rejected(values, "YC_PROJECTION_STATUS_INVALID")

    def test_calendar_and_nanosecond_timestamp_profile(self):
        for stamp in ("2026-02-30T10:00:00Z", "0000-01-01T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:00:60Z",
                      "2026-01-01T00:00:00.1234567890Z", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00z", "2026-01-01", None, 123):
            with self.subTest(stamp=stamp):
                values = responses()
                values[2]["createdAt"] = stamp
                self.assert_rejected(values, "YC_PROJECTION_TIME_INVALID")
        for stamp in ("2024-02-29T00:00:00Z", "2026-01-01T00:00:00.1Z", "9999-12-31T23:59:59.999999999Z"):
            values = responses()
            values[2]["createdAt"] = stamp
            self.assertEqual(project(values)["snapshot"]["created_at"], stamp)

    def test_id_profile_does_not_accept_controls_unicode_or_options(self):
        for value in ("", " ", "a b", "x\x00", "--id", "x\n", "x\x1b", "кириллица", "a" * 51, True, None):
            with self.subTest(value=value):
                selection = projection.SnapshotSelection(value, SELECTION.vm_id, SELECTION.disk_id, SELECTION.snapshot_id)
                with self.assertRaises(projection.ProjectionError) as ctx:
                    project(selection=selection)
                self.assertEqual(str(ctx.exception), "YC_PROJECTION_ID_INVALID")

    def test_response_selection_required_fields_cannot_be_caller_trust_flags(self):
        for selection in (None, {"trusted": True, "approved": True}, tuple(SELECTION.__dict__.values())):
            with self.assertRaises(projection.ProjectionError) as ctx:
                project(selection=selection)
            self.assertEqual(str(ctx.exception), "YC_PROJECTION_SELECTION_REQUIRED")
        for index, fields in ((0, ("id", "folderId", "bootDisk")),
                              (1, ("id", "folderId", "size", "status", "typeId", "zoneId", "instanceIds")),
                              (2, ("id", "folderId", "diskSize", "status", "sourceDiskId", "createdAt"))):
            for field in fields:
                values = responses()
                del values[index][field]
                self.assert_rejected(values, "YC_PROJECTION_FIELD_MISSING")

    def test_json_rejects_ambiguity_and_never_returns_parser_exception_context(self):
        valid = [encode(value) for value in responses()]
        payloads = (b"", b"\xff", b"{", b"[]", b"null", b"true", b"{} {}", b'{"id":"a","i\\u0064":"b"}',
                    b'{"private":"SYNTHETIC_PRIVATE_SENTINEL","n":NaN}', b'{"n":Infinity}', b'{"n":1e309}',
                    b'{"n":1.5}', b'{"n":"\\ud800"}', b'{"n":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
                    b" " * (projection.MAX_RESPONSE_BYTES + 1))
        for payload in payloads:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(projection.ProjectionError) as ctx:
                    projection.project_snapshot_context(payload, *valid[1:], selection=SELECTION)
                self.assertIsNone(ctx.exception.__context__)
                self.assertNotIn(PRIVATE, repr(ctx.exception))
                self.assertRegex(str(ctx.exception), r"^YC_PROJECTION_[A-Z_]+$")

    def test_input_limits_and_immutable_byte_boundary(self):
        for payload in ("{}", {}, bytearray(b"{}"), None):
            with self.assertRaises(projection.ProjectionError) as ctx:
                projection.project_snapshot_context(payload, b"{}", b"{}", selection=SELECTION)
            self.assertEqual(str(ctx.exception), "YC_PROJECTION_BYTES_REQUIRED")
        for extra in ([0] * (projection.MAX_JSON_NODES + 1),):
            values = responses()
            values[0]["ignored"] = extra
            self.assert_rejected(values, "YC_PROJECTION_JSON_LIMIT")
        values = responses()
        nested = 0
        for _ in range(projection.MAX_JSON_DEPTH + 1):
            nested = [nested]
        values[0]["ignored"] = nested
        self.assert_rejected(values, "YC_PROJECTION_JSON_LIMIT")

    def test_snake_case_and_mixed_identity_representations_reject(self):
        for index, alias in ((0, "folder_id"), (1, "instance_ids"), (2, "source_disk_id"), (2, "created_at")):
            values = responses()
            values[index][alias] = "synthetic-other"
            self.assert_rejected(values, "YC_PROJECTION_REPRESENTATION_UNSUPPORTED")
        for role in ("bootDisk", "secondaryDisks"):
            values = responses()
            if role == "bootDisk":
                values[0][role]["disk_id"] = "synthetic-other"
            else:
                values[0][role] = [{"diskId": "synthetic-other", "disk_id": SELECTION.disk_id}]
            self.assert_rejected(values, "YC_PROJECTION_REPRESENTATION_UNSUPPORTED")

    def test_untrusted_evidence_and_unknown_fields_never_create_consent(self):
        values = responses()
        for value in values:
            value.update({"approved": True, "trusted": True, "evidence_source": "owner_console", "authorization_granted": True,
                          "independent_guard_readback": True, "restore_verified": True})
        result = project(values)
        self.assertFalse(result["authorization_granted"])
        self.assertFalse(result["independent_guard_readback"])
        self.assertFalse(result["restore_verified"])
        self.assertNotIn("approved", result)

    def test_result_is_detached_from_input_and_other_results(self):
        values = responses()
        original = copy.deepcopy(values)
        left = project(values)
        left["disk"]["instance_ids"].append("synthetic-other")
        self.assertEqual(values, original)
        self.assertEqual(project(values)["disk"]["instance_ids"], [SELECTION.vm_id])

    def test_projection_is_not_packaged_or_a_new_policy_allow(self):
        self.assertNotIn("tools/yc_read_projection.py", artifact.BUNDLE_SOURCES.values())
        executable = {"invoked": "yc", "resolved_path": "C:/synthetic/yc.exe", "object_identity": "synthetic:yc"}
        for resource in ("disk", "snapshot"):
            fact = {"schema": "parsed-simple/v1", "platform": "windows", "parser": {"status": "exact"},
                    "executable": executable, "argv": ["yc", "compute", resource, "get", "--id", "synthetic-" + resource],
                    "cwd": {"lexical": "C:/synthetic", "object_identity": "synthetic:cwd", "follow_mode": "target"},
                    "projection": project()}
            self.assertEqual(classifier_yc.analyze_yc(fact)["decision"], "ASK_USER")


if __name__ == "__main__":
    unittest.main()

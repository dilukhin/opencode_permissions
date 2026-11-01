"""Bounded, offline projection of Compute REST response fields.

This is data validation, not authorization or independent cloud read-back.
No process, credential, policy or approval transport is used by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any

MAX_RESPONSE_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 2048
MAX_ATTACHMENTS = 64
MAX_INT64 = (1 << 63) - 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,49}\Z", re.ASCII)
_SIZE = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z\Z", re.ASCII)
_STATUSES = frozenset({"CREATING", "READY", "ERROR", "DELETING"})


class ProjectionError(ValueError):
    """Only a fixed code; never retain response text, keys or resource values."""


@dataclass(frozen=True)
class SnapshotSelection:
    """Expected values for comparison, never a capability or consent receipt."""
    folder_id: str
    vm_id: str
    disk_id: str
    snapshot_id: str


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProjectionError(code)


def _id(value: Any) -> str:
    _require(type(value) is str and _ID.fullmatch(value) is not None, "YC_PROJECTION_ID_INVALID")
    return value


def _size(value: Any) -> str:
    _require(type(value) is str and _SIZE.fullmatch(value) is not None, "YC_PROJECTION_SIZE_INVALID")
    _require(int(value) <= MAX_INT64, "YC_PROJECTION_SIZE_INVALID")
    return value


def _timestamp(value: Any) -> str:
    _require(type(value) is str and _TIME.fullmatch(value) is not None, "YC_PROJECTION_TIME_INVALID")
    invalid = False
    try:
        # Keep the original nanosecond precision; datetime validates only the
        # calendar/time portion and is not used to re-serialize the timestamp.
        datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        invalid = True
    if invalid:
        raise ProjectionError("YC_PROJECTION_TIME_INVALID")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value: str) -> Any:
    raise ValueError("non-finite JSON number")


def _decode(payload: bytes) -> dict[str, Any]:
    _require(type(payload) is bytes, "YC_PROJECTION_BYTES_REQUIRED")
    _require(0 < len(payload) <= MAX_RESPONSE_BYTES, "YC_PROJECTION_RESPONSE_SIZE_INVALID")
    failed = False
    value = None
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant, parse_float=_constant)
    except (UnicodeError, ValueError, RecursionError):
        failed = True
    # Raise outside the except block: JSONDecodeError retains the raw document
    # and must not become the context of an exception returned to a consumer.
    if failed:
        raise ProjectionError("YC_PROJECTION_JSON_INVALID")
    _require(type(value) is dict, "YC_PROJECTION_OBJECT_REQUIRED")
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        _require(nodes <= MAX_JSON_NODES and depth <= MAX_JSON_DEPTH, "YC_PROJECTION_JSON_LIMIT")
        if type(item) is dict:
            for key, child in item.items():
                pending.append((key, depth + 1))
                pending.append((child, depth + 1))
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            _require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), "YC_PROJECTION_UNICODE_INVALID")
    return value


def _field(obj: dict[str, Any], name: str) -> Any:
    _require(name in obj, "YC_PROJECTION_FIELD_MISSING")
    return obj[name]


def _object(value: Any) -> dict[str, Any]:
    _require(type(value) is dict, "YC_PROJECTION_FIELD_TYPE_INVALID")
    return value


def _status(obj: dict[str, Any]) -> str:
    value = _field(obj, "status")
    _require(type(value) is str and value in _STATUSES, "YC_PROJECTION_STATUS_INVALID")
    return value


def _match_resource(obj: dict[str, Any], resource_id: str, folder_id: str) -> None:
    _require(_id(_field(obj, "id")) == resource_id, "YC_PROJECTION_RESOURCE_MISMATCH")
    _require(_id(_field(obj, "folderId")) == folder_id, "YC_PROJECTION_FOLDER_MISMATCH")


def _attachment(vm: dict[str, Any], disk_id: str) -> str:
    matches = []
    boot = _object(_field(vm, "bootDisk"))
    _require("disk_id" not in boot, "YC_PROJECTION_REPRESENTATION_UNSUPPORTED")
    if _id(_field(boot, "diskId")) == disk_id:
        matches.append("boot")
    secondary = vm.get("secondaryDisks", [])
    _require(type(secondary) is list and len(secondary) <= MAX_ATTACHMENTS, "YC_PROJECTION_ATTACHMENTS_INVALID")
    observed = {boot["diskId"]}
    for item in secondary:
        item = _object(item)
        _require("disk_id" not in item, "YC_PROJECTION_REPRESENTATION_UNSUPPORTED")
        current = _id(_field(item, "diskId"))
        _require(current not in observed, "YC_PROJECTION_ATTACHMENTS_INVALID")
        observed.add(current)
        if current == disk_id:
            matches.append("secondary")
    _require(len(matches) == 1, "YC_PROJECTION_VM_DISK_MISMATCH")
    return matches[0]


def project_snapshot_context(
    vm_response: bytes,
    disk_response: bytes,
    snapshot_response: bytes,
    *,
    selection: SnapshotSelection,
) -> dict[str, Any]:
    """Compare three REST JSON objects and return only the fixed field set.

    A successful comparison does not authenticate inputs, prove freshness or
    authorize a read/mutation. Scope authorization must precede any real read.
    This profile excludes shared disks, resizing between observations and
    non-UTC timestamps. A rejection is not a diagnosis of the cloud resource.
    """
    _require(type(selection) is SnapshotSelection, "YC_PROJECTION_SELECTION_REQUIRED")
    folder_id, vm_id, disk_id, snapshot_id = (
        _id(selection.folder_id), _id(selection.vm_id), _id(selection.disk_id), _id(selection.snapshot_id),
    )
    vm, disk, snapshot = (_decode(raw) for raw in (vm_response, disk_response, snapshot_response))
    # This component accepts REST camelCase only. Reject mixed aliases rather
    # than silently preferring one representation of an identity-bearing field.
    for obj in (vm, disk, snapshot):
        _require(not {"folder_id", "boot_disk", "secondary_disks", "instance_ids", "source_disk_id", "disk_size", "created_at", "type_id", "zone_id"}.intersection(obj),
                 "YC_PROJECTION_REPRESENTATION_UNSUPPORTED")
    _match_resource(vm, vm_id, folder_id)
    _match_resource(disk, disk_id, folder_id)
    _match_resource(snapshot, snapshot_id, folder_id)
    attachment = _attachment(vm, disk_id)
    instance_ids = _field(disk, "instanceIds")
    _require(type(instance_ids) is list and len(instance_ids) == 1,
             "YC_PROJECTION_DISK_VM_MISMATCH")
    _require(_id(instance_ids[0]) == vm_id, "YC_PROJECTION_DISK_VM_MISMATCH")
    _require(_id(_field(snapshot, "sourceDiskId")) == disk_id, "YC_PROJECTION_SOURCE_DISK_MISMATCH")
    disk_size, snapshot_size = _size(_field(disk, "size")), _size(_field(snapshot, "diskSize"))
    _require(disk_size == snapshot_size, "YC_PROJECTION_SIZE_CONTEXT_CHANGED")
    disk_status, snapshot_status = _status(disk), _status(snapshot)
    return {
        "schema": "yc-snapshot-projection/v1",
        "representation": "compute-rest-json/v1",
        "vm": {"id": vm_id, "folder_id": folder_id, "selected_disk_role": attachment},
        "disk": {
            "id": disk_id, "folder_id": folder_id, "status": disk_status, "size": disk_size,
            "type_id": _id(_field(disk, "typeId")), "zone_id": _id(_field(disk, "zoneId")),
            "instance_ids": [vm_id],
        },
        "snapshot": {
            "id": snapshot_id, "folder_id": folder_id, "status": snapshot_status,
            "source_disk_id": disk_id, "disk_size": snapshot_size,
            "created_at": _timestamp(_field(snapshot, "createdAt")),
        },
        "snapshot_ready": disk_status == snapshot_status == "READY",
        "authorization_granted": False,
        "independent_guard_readback": False,
        "restore_verified": False,
    }

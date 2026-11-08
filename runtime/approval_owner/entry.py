"""Protected native bootstrap entry. No approval arguments or alternate executor."""
from __future__ import annotations

import getpass
import hashlib
import json
from pathlib import Path
import queue
import re
import sys
import time

# -I -S excludes the entry directory. Native bootstrap holds this entire runtime
# and its parent directory; never add cwd/user site/an agent-selected import path.
RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))

from approval_owner.console import review
from approval_owner.ledger import strict_json
from approval_owner.read_host import ReadHost
import windows_owner_boundary as boundary
from yc_owner_windows_context import WindowsReadContext
from yc_read_projection import SnapshotSelection
from yc_snapshot_read import ReadError, canonical, require


def run(config_path):
    require(len(sys.argv) == 2 and sys.stdin.isatty() and sys.stdout.isatty(), "YC_OWNER_LOCAL_TERMINAL_REQUIRED")
    raw = Path(config_path).read_bytes()
    config = strict_json(raw)
    require(set(config) == {"schema", "owner_sid", "agent_sid", "component_id", "component_manifest_sha256",
                            "yc_path", "cwd", "pipe_prefix"}, "YC_OWNER_BOOTSTRAP_CONFIG_INVALID")
    require(config["schema"] == "yc-owner-bootstrap/v1", "YC_OWNER_BOOTSTRAP_CONFIG_INVALID")
    actor = boundary.current()
    require(actor.session_id != 0 and actor.sid == config["owner_sid"] and actor.sid != config["agent_sid"],
            "YC_OWNER_BOOTSTRAP_ACTOR_INVALID")
    manifest_raw = (RUNTIME.parent / "manifest.json").read_bytes()
    require(hashlib.sha256(manifest_raw).hexdigest() == config["component_manifest_sha256"],
            "YC_OWNER_MANIFEST_CHANGED")
    manifest = strict_json(manifest_raw)
    require(manifest["artifact_id"] == config["component_id"] and manifest["execution_enabled"] is True
            and manifest["status"] == "managed_owner_candidate", "YC_OWNER_COMPONENT_NOT_ACTIVATABLE")
    pins = {row["path"]: row["sha256"] for row in manifest["files"]}
    require(re.fullmatch(r"yc59-[0-9a-f]{32}", config["pipe_prefix"]) is not None,
            "YC_OWNER_BOOTSTRAP_CONFIG_INVALID")
    print("Владелец разрешений: чтение одной ВМ, диска и снимка по точным ID.")
    print("Секреты вводятся только здесь. В OpenCode и отчёт они не передаются.")
    token = getpass.getpass("IAM-токен владельца (ввод скрыт): ")
    values = {}
    for key, label in (("cloud_id", "Облако"), ("folder_id", "Каталог"), ("vm_id", "ВМ"),
                       ("disk_id", "Диск"), ("snapshot_id", "Снимок")):
        value = input(label + " — ID: ").strip()
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,50}", value) is not None, "YC_OWNER_SELECTION_INVALID")
        values[key] = value
    observed = time.monotonic()
    selection = SnapshotSelection(*(values[k] for k in ("folder_id", "vm_id", "disk_id", "snapshot_id")))
    sources = WindowsReadContext(selection=selection, cloud_id=values["cloud_id"], observed_monotonic=observed,
        yc_path=config["yc_path"], cwd=config["cwd"],
        native_policy_path=str(RUNTIME.parent / "policy/native/rules.v1.json"),
        yc_policy_path=str(RUNTIME.parent / "policy/yc/yc_policy.v1.json"),
        native_sha256=pins["policy/native/rules.v1.json"], yc_policy_sha256=pins["policy/yc/yc_policy.v1.json"],
        iam_token=token)
    del token
    def show_results(host):
        while True:
            try:
                result = host.completed.get_nowait()
            except queue.Empty:
                return
            print(json.dumps({"schema": "yc-owner-result/v1", "component_id": config["component_id"],
                              "result": result, "result_sha256": hashlib.sha256(canonical(result)).hexdigest()},
                             ensure_ascii=True, sort_keys=True), flush=True)
    try:
        with ReadHost(config["pipe_prefix"], config["agent_sid"], current_context=sources.current,
                      native_check=sources.veto.check, start=sources.start) as host:
            print(json.dumps({"schema": "yc-owner-live-endpoint/v1", "component_id": config["component_id"],
                              "owner_sid": actor.sid, "owner_session_id": actor.session_id,
                              "agent_sid": config["agent_sid"], "server_pid": __import__("os").getpid(),
                              "pipe_prefix": config["pipe_prefix"], "approval_required": True}, ensure_ascii=True))
            while time.monotonic() - observed < 60 and not host.stopping.is_set() and not host.transport.failed.is_set():
                show_results(host)
                try:
                    bound = host.pending.get(timeout=.2)
                except queue.Empty:
                    continue
                def owner_call(request):
                    return strict_json(host.handle("decision", boundary.current(), json.dumps(request).encode("ascii")))
                review(owner_call, bound["request_id"], bound["operation_sha256"], terminal=True,
                       owner_actor=actor, agent_sid=config["agent_sid"])
            print("Сеанс владельца завершён. Оставшиеся согласия отменены.")
        show_results(host)  # include a result finished at the closing boundary
    finally:
        sources.close()


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2, "YC_OWNER_BOOTSTRAP_REQUIRED")
        run(sys.argv[1])
    except (Exception, KeyboardInterrupt):
        # No raw config/credential/API/traceback diagnostics cross the boundary.
        print("YC_OWNER_SESSION_REFUSED", file=sys.stderr)
        raise SystemExit(2) from None

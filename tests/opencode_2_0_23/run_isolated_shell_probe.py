"""Linux-fixture: настоящий Session.shell под отдельным UID, без допуска sudo-job."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import threading

from run_boundary_probe import SOURCE_SHA, VERSION, probe, require


class IsolatedShell:
    """Временный root launcher запускает только локальные команды под tools UID.

    Не является broker согласия: launcher не выдаёт grants и не выполняет SSH.
    Host может выбрать любую команду, но не UID, env или root operation.
    """

    def __init__(self):
        require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_FIXTURE_REQUIRED")
        self.host = pwd.getpwnam("daemon")
        self.tools = pwd.getpwnam("nobody")
        require(self.host.pw_uid != self.tools.pw_uid and self.host.pw_uid != 0, "UIDS_NOT_SEPARATE")
        self.done = threading.Event()
        self.listener = None
        self.thread = None
        self.error = None

    def configure(self, root, environment, binary):
        root.chmod(0o755)
        for name in ("home", "config", "xdg-config", "xdg-data", "xdg-cache", "xdg-state"):
            directory = root / name
            directory.mkdir(mode=0o700, exist_ok=True)
            os.chown(directory, self.host.pw_uid, self.host.pw_gid)
        project = root / "project"
        os.chown(project, self.host.pw_uid, self.tools.pw_gid)
        project.chmod(0o770)
        tool_home = root / "tool-home"
        tool_home.mkdir(mode=0o700)
        os.chown(tool_home, self.tools.pw_uid, self.tools.pw_gid)
        protected = root / "home" / "synthetic-private-marker"
        protected.write_bytes(b"synthetic fixture data; no credential")
        protected.chmod(0o600)
        os.chown(protected, self.host.pw_uid, self.host.pw_gid)
        child = root / "child_reply_probe.py"
        shutil.copyfile(Path(__file__).with_name(child.name), child)
        child.chmod(0o644)
        dropper = root / "drop-tools.py"
        dropper.write_text(
            "import ctypes, os, sys\n"
            f"os.setgroups([])\nos.setgid({self.tools.pw_gid})\nos.setuid({self.tools.pw_uid})\n"
            "libc = ctypes.CDLL(None, use_errno=True)\n"
            "if libc.prctl(38, 1, 0, 0, 0) != 0: raise RuntimeError('NO_NEW_PRIVS_FAILED')\n"
            "os.execv('/bin/sh', ['/bin/sh', '-c', sys.argv[1]])\n", encoding="utf-8",
        )
        dropper.chmod(0o644)
        address = root / "shell-launcher.sock"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(address))
        os.chown(address, self.host.pw_uid, self.host.pw_gid)
        address.chmod(0o600)
        self.listener.listen(1)
        self.listener.settimeout(0.2)
        wrapper = root / "isolated-shell"
        wrapper.write_text(
            "#!/usr/bin/python3\nimport base64, json, socket, sys\n"
            "if len(sys.argv) != 3 or sys.argv[1] != '-c': raise SystemExit(126)\n"
            "with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:\n"
            f"    s.connect({str(address)!r})\n"
            "    s.sendall(json.dumps({'command': sys.argv[2]}).encode() + b'\\n')\n"
            "    with s.makefile('rb') as f: result = json.loads(f.readline(1048576))\n"
            "sys.stdout.buffer.write(base64.b64decode(result['stdout']))\n"
            "sys.stderr.buffer.write(base64.b64decode(result['stderr']))\n"
            "raise SystemExit(result['returncode'])\n", encoding="utf-8",
        )
        wrapper.chmod(0o755)
        environment["SHELL"] = str(wrapper)
        self.environment = {"PATH": "/usr/bin:/bin", "HOME": str(tool_home), "PYTHONIOENCODING": "utf-8"}
        self.project, self.dropper = project, dropper
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        return child, ["--protected-file", str(protected), "--launcher-socket", str(address)], {
            "user": self.host.pw_uid, "group": self.host.pw_gid, "extra_groups": [],
        }

    def serve(self):
        try:
            while not self.done.is_set():
                try:
                    connection, _ = self.listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(5)
                    _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    require(uid == self.host.pw_uid, "LAUNCHER_CALLER_UID_MISMATCH")
                    with connection.makefile("rb") as stream:
                        raw = stream.readline(65537)
                    require(raw.endswith(b"\n") and len(raw) <= 65536, "LAUNCHER_INPUT_LIMIT")
                    request = json.loads(raw)
                    require(set(request) == {"command"} and isinstance(request["command"], str), "LAUNCHER_INPUT_INVALID")
                    result = subprocess.run(
                        ["/usr/bin/python3", str(self.dropper), request["command"]],
                        cwd=self.project, env=self.environment, stdin=subprocess.DEVNULL,
                        capture_output=True, timeout=25,
                    )
                    require(len(result.stdout) + len(result.stderr) < 500000, "LAUNCHER_OUTPUT_LIMIT")
                    connection.sendall(json.dumps({
                        "returncode": result.returncode,
                        "stdout": base64.b64encode(result.stdout).decode(),
                        "stderr": base64.b64encode(result.stderr).decode(),
                    }).encode() + b"\n")
        except Exception as error:
            # Ошибка сохраняется без argv/credential и повторно выбрасывается в owner.
            self.error = type(error).__name__

    def verify(self, child):
        require(self.error is None, "LAUNCHER_FAILED")
        require(child["child_uid"] == self.tools.pw_uid, "REAL_SHELL_UID_NOT_ISOLATED")
        require(child["child_groups"] == [], "SUPPLEMENTARY_GROUPS_INHERITED")
        require(child["no_new_privileges"] == 1, "PRIVILEGE_ESCALATION_NOT_DISABLED")
        require(child["credential_source_count"] == 0, "CHILD_OBTAINED_CREDENTIAL")
        require(child["proc_readable"] is False, "SERVER_PROC_READABLE")
        require(child["protected_file_readable"] is False, "HOST_PRIVATE_FILE_READABLE")
        require(child["launcher_socket_accessible"] is False, "TOOLS_CAN_CALL_HOST_LAUNCHER")
        require(child["unauthenticated_reply_status"] == 401, "CHILD_UNAUTHENTICATED_REPLY_ACCEPTED")
        require(child["reply_accepted"] is False, "ISOLATED_CHILD_CAN_REPLY")

    def close(self):
        self.done.set()
        if self.thread is not None:
            self.thread.join(timeout=30)
            require(not self.thread.is_alive(), "LAUNCHER_THREAD_NOT_TERMINATED")
        if self.listener is not None:
            self.listener.close()
        require(self.error is None, "LAUNCHER_FAILED")


def self_check():
    # Отдельная проверка реальной Linux-изоляции; не заменяет опыт OpenCode.
    with tempfile.TemporaryDirectory(prefix="isolated-shell-self-check-") as temporary:
        root = Path(temporary)
        for name in ("home", "config", "project"):
            (root / name).mkdir()
        fixture = IsolatedShell()
        environment = {}
        _, extra, process_options = fixture.configure(root, environment, None)
        protected, address = extra[1], extra[3]
        command = "/usr/bin/python3 -c " + shlex.quote(
            "import json, os, socket; from pathlib import Path; "
            "s=socket.socket(socket.AF_UNIX); "
            f"p=Path({protected!r}); "
            "print(json.dumps({'uid':os.getuid(), 'groups':os.getgroups(), "
            "'host_directory_access':os.access(p.parent,os.R_OK), "
            f"'launcher_access':os.access({address!r},os.W_OK), "
            "'credential_present':'OPENCODE_PASSWORD' in os.environ}))"
        )
        try:
            result = subprocess.run([environment["SHELL"], "-c", command], cwd=root / "project",
                                    env={"PATH": "/usr/bin:/bin", "OPENCODE_PASSWORD": "synthetic"},
                                    capture_output=True, text=True, timeout=30, **process_options)
            require(result.returncode == 0, "SELF_CHECK_LAUNCH_FAILED")
            report = json.loads(result.stdout)
            require(report == {"uid": fixture.tools.pw_uid, "groups": [], "host_directory_access": False,
                               "launcher_access": False, "credential_present": False}, "SELF_CHECK_FAILED")
            print(json.dumps({"linux_fixture_self_check": True, "opencode_runtime_proof": False, **report}))
        finally:
            fixture.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    require(args.binary is not None and args.source is not None and args.output is not None, "PROBE_ARGUMENTS_MISSING")
    version = subprocess.run([str(args.binary.resolve()), "--version"], capture_output=True, text=True, timeout=15)
    require(version.returncode == 0 and version.stdout.strip() == f"opencode v{VERSION}", "BINARY_VERSION_MISMATCH")
    require(json.loads((args.source / "package.json").read_text())["version"] == VERSION, "SOURCE_VERSION_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="opencode-isolated-binary-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        binary = root / "opencode"
        shutil.copyfile(args.binary, binary)
        binary.chmod(0o755)
        modes = [probe(binary, mode, IsolatedShell()) for mode in ("default", "stdio")]
        report = {
            "schema": "opencode-2-linux-isolated-shell/v1", "version": VERSION, "source_sha": SOURCE_SHA,
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "modes": modes,
            "host_uid": pwd.getpwnam("daemon").pw_uid, "tools_uid": pwd.getpwnam("nobody").pw_uid,
            "isolation_scope": "Session.shell only; root-owned test launcher, not approval broker",
            "actual_human_ui_proof": False, "untrusted_plugin_runtime_proof": False,
            "native_sudo_job_admission_ready": False, "remote_mutations": False,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"isolated_shell_probe_completed": True, "native_sudo_job_admission_ready": False,
                      "child_can_reply": {item["mode"]: item["child"]["reply_accepted"] for item in modes},
                      "child_proc_readable": {item["mode"]: item["child"]["proc_readable"] for item in modes}}))


if __name__ == "__main__":
    main()

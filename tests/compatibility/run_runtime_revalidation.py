#!/usr/bin/env python3
"""Run the established DC-4 permission lifecycle scenarios on an exact rolling target.

The historical DC-4 harness remains pinned to 1.18.26. This wrapper reuses its
non-destructive scenarios only after the rolling compatibility gate has selected
an exact target version and official binary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

DC4_DIR = Path(__file__).resolve().parents[1] / "dc4_runtime"
sys.path.insert(0, str(DC4_DIR))
import run_probe as dc4  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()

    version = subprocess.run(
        [args.opencode, "--version"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if version != args.expected_version:
        raise SystemExit(
            f"rolling runtime revalidation expected OpenCode {args.expected_version}, got {version!r}"
        )

    repo_root = Path(args.repo_root).resolve()
    results = [dc4.run_scenario(args.opencode, repo_root, name) for name in dc4.SCENARIOS]
    print(
        json.dumps(
            {
                "schema": "opencode-rolling-runtime-proof/v1",
                "opencode_version": version,
                "reused_scenario_contract": "dc4-runtime-proof/v1",
                "results": results,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

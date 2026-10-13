#!/usr/bin/env python3
"""Acquire only the official, hash-pinned Q1 test binary on disposable CI."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("question_1_19_0_assets.json").read_text())
    asset = manifest["assets"][os.name]
    url = f"https://github.com/anomalyco/opencode/releases/download/v{manifest['opencode_version']}/{asset['name']}"
    with urllib.request.urlopen(url, timeout=90) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != asset["sha256"]:
        raise SystemExit("Q1 official archive digest mismatch")
    name = "opencode.exe" if os.name == "nt" else "opencode"
    if os.name == "nt":
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            candidates = [i for i in zipped.infolist() if not i.is_dir() and Path(i.filename).name == name]
            if len(candidates) != 1:
                raise SystemExit("Q1 official archive must contain one binary")
            content = zipped.read(candidates[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            candidates = [i for i in tar.getmembers() if i.isfile() and Path(i.name).name == name]
            if len(candidates) != 1:
                raise SystemExit("Q1 official archive must contain one binary")
            content = tar.extractfile(candidates[0]).read()
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / name
    target.write_bytes(content)
    target.chmod(0o755)
    print(f"Verified OpenCode {manifest['opencode_version']} archive SHA-256")


if __name__ == "__main__":
    main()

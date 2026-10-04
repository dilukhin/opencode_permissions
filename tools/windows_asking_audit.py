"""Count narrowly recognized OpenCode 1.18.32 Windows bash ASK patterns.

Reads the local log once and emits only aggregate counts. Never prints a pattern,
argument, path, or unrecognized input. This is an audit, not a permission policy.
"""

import json
import re
from collections import Counter
from pathlib import Path


ASKING = re.compile(r"(?:^|\s)message=asking(?:\s|$)")
BASH = re.compile(r"(?:^|\s)permission=bash(?:\s|$)")
PATTERNS = re.compile(r"(?:^|\s)patterns=")
TIMESTAMP = re.compile(r"(?:^|\s)timestamp=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z)(?:\s|$)")

# Exact, argument-free or fixed-argument forms only. These are candidates for
# review; a count never grants permission or proves an effective policy.
CANDIDATES = (
    "pwd",
    "git status",
    "git status --short",
    "git status -sb",
    "git rev-parse HEAD",
    "git rev-parse --show-toplevel",
    "git log -5 --oneline",
    "git show --stat HEAD",
)

# Diagnostic labels, not safety decisions. Prefix checks can overcount a
# family when a command contains shell operators or opaque arguments.
FAMILIES = (
    "git.status", "git.diff", "git.log", "git.show", "git.rev-parse",
    "git.branch", "git.remote", "git.other", "rg", "grep",
    "powershell.read", "powershell.search", "powershell.inspect",
    "powershell.other", "python", "node", "build", "network",
    "other",
)


def family(pattern):
    command = pattern.lstrip().lower()
    git = re.match(r"git(?:\.exe)?(?:\s+|$)([^\s]+)?", command)
    if git:
        verb = git.group(1)
        return "git." + verb if verb in {
            "status", "diff", "log", "show", "rev-parse", "branch", "remote"
        } else "git.other"
    executable = re.match(r"([a-z][a-z0-9_.-]*)(?:\s|$)", command)
    if not executable:
        return "other"
    verb = executable.group(1)
    if verb in ("rg", "rg.exe"):
        return "rg"
    if verb in ("grep", "grep.exe"):
        return "grep"
    if verb in ("get-content", "get-childitem", "get-child-item", "get-item", "get-location", "test-path"):
        return "powershell.read"
    if verb in ("select-string",):
        return "powershell.search"
    if verb in ("get-command", "get-filehash", "get-acl"):
        return "powershell.inspect"
    if verb in ("powershell", "powershell.exe", "pwsh", "pwsh.exe", "cmd", "cmd.exe"):
        return "powershell.other"
    if verb in ("python", "python.exe", "python3", "py", "pytest"):
        return "python"
    if verb in ("node", "node.exe", "npm", "npx", "bun"):
        return "node"
    if verb in ("cmake", "ctest", "dotnet", "go", "make", "ninja"):
        return "build"
    if verb in ("ssh", "scp", "curl", "wget", "invoke-webrequest", "invoke-restmethod"):
        return "network"
    return "other"


def parse_patterns(line):
    """OpenCode logs patterns as JSON-quoted JSON; accept bare JSON too."""
    match = PATTERNS.search(line)
    if not match:
        return None
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(line[match.end():].lstrip())
        if isinstance(value, str):
            value = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
        return None
    return value


def audit(lines):
    counts = Counter()
    candidates = Counter()
    single = Counter()
    multi_any = Counter()
    multi_all = Counter()
    multi_sizes = Counter()
    first = last = None
    for line in lines:
        counts["lines"] += 1
        if not ASKING.search(line):
            continue
        counts["asking"] += 1
        if not BASH.search(line):
            continue
        counts["bash"] += 1
        stamp = TIMESTAMP.search(line)
        if stamp:
            first = stamp.group(1) if first is None else first
            last = stamp.group(1)
        patterns = parse_patterns(line)
        if patterns is None:
            counts["invalid_patterns"] += 1
        elif len(patterns) != 1:
            counts["multiple_patterns"] += 1
            labels = {family(pattern) for pattern in patterns}
            multi_any.update(labels)
            if len(labels) == 1:
                multi_all.update(labels)
            if len(patterns) == 2:
                multi_sizes["2"] += 1
            elif len(patterns) == 3:
                multi_sizes["3"] += 1
            elif len(patterns) <= 7:
                multi_sizes["4-7"] += 1
            else:
                multi_sizes["8+"] += 1
        elif patterns[0] in CANDIDATES:
            candidates[patterns[0]] += 1
            counts["exact_candidate"] += 1
            single[family(patterns[0])] += 1
        else:
            counts["other_single_pattern"] += 1
            single[family(patterns[0])] += 1
    total = counts["bash"]
    unknown = total - counts["exact_candidate"]
    return {
        "schema": 1,
        "scope": "OpenCode 1.18.32 Windows message=asking permission=bash; not visible prompt count",
        "lines": counts["lines"],
        "asking": counts["asking"],
        "bash": total,
        "first_bash_utc": first,
        "last_bash_utc": last,
        "exact_candidates": {key: candidates[key] for key in CANDIDATES},
        "exact_candidate_total": counts["exact_candidate"],
        "multiple_patterns": counts["multiple_patterns"],
        "other_single_pattern": counts["other_single_pattern"],
        "invalid_patterns": counts["invalid_patterns"],
        "family_single": {key: single[key] for key in FAMILIES},
        "family_multi_any": {key: multi_any[key] for key in FAMILIES},
        "family_multi_all": {key: multi_all[key] for key in FAMILIES},
        "multi_size": {key: multi_sizes[key] for key in ("2", "3", "4-7", "8+")},
        "unknown": unknown,
        "unknown_percent": round(100 * unknown / total, 1) if total else None,
        "checksum_ok": total == counts["exact_candidate"] + counts["multiple_patterns"]
        + counts["other_single_pattern"] + counts["invalid_patterns"],
    }


def main():
    path = Path.home() / ".local" / "share" / "opencode" / "log" / "opencode.log"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as source:
            result = audit(source)
    except OSError:
        raise SystemExit("OpenCode log unavailable; no counts produced") from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

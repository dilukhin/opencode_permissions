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
        elif patterns[0] in CANDIDATES:
            candidates[patterns[0]] += 1
            counts["exact_candidate"] += 1
        else:
            counts["other_single_pattern"] += 1
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

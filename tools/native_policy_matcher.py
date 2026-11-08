"""Shared OpenCode V1 wildcard/last-match semantics; no shell parser or grants."""
import re

def wildcard_match(value, pattern, platform="posix"):
    value=value.replace("\\","/")
    pattern=pattern.replace("\\","/")
    escaped=re.sub(r'([.+^${}()|\[\]\\])',r'\\\1',pattern)
    escaped=escaped.replace("*",".*").replace("?",".")
    if escaped.endswith(" .*"):
        escaped=escaped[:-3]+"( .*)?"
    flags=re.S | (re.I if platform=="win32" else 0)
    return re.fullmatch(escaped,value,flags) is not None


def evaluate_pattern(permission, pattern, rules, platform="posix"):
    matched=[
        r for r in rules
        if wildcard_match(permission,r["permission"],platform)
        and wildcard_match(pattern,r["pattern"],platform)
    ]
    if not matched:
        return {"action":"ask","rule_id":"implicit.default.ask","matched_rule_ids":[]}
    return {
        "action":matched[-1]["action"],"rule_id":matched[-1]["id"],
        "matched_rule_ids":[r["id"] for r in matched],
    }


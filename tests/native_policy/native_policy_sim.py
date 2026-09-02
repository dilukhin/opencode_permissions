#!/usr/bin/env python3
"""Test-only OpenCode V1 native permission matcher simulator.

It does not parse shell commands or classify effects. It only evaluates explicit,
already-extracted permission/pattern fixtures.
"""
import argparse, json, re
from pathlib import Path

def wildcard_match(value, pattern, platform="posix"):
    value=value.replace("\\","/")
    pattern=pattern.replace("\\","/")
    escaped=re.sub(r'([.+^${}()|\[\]\\])',r'\\\1',pattern)
    escaped=escaped.replace("*",".*").replace("?",".")
    if escaped.endswith(" .*"):
        escaped=escaped[:-3]+"( .*)?"
    flags=re.S | (re.I if platform=="win32" else 0)
    return re.fullmatch(escaped,value,flags) is not None

def expand_rules(policy):
    return [
        {"id":row[0],"permission":row[1],"pattern":row[2],"action":row[3]}
        for row in policy["rules"]
    ]

def expand_cases(projection):
    out=[]
    for row in projection["cases"]:
        out.append({
            "id":row[0],"safety_expectation":row[1],"scope":row[2],
            "native_requests":[{"permission":r[0],"patterns":r[1]} for r in row[3]],
            "tags":row[4],"note":row[5],
        })
    return out

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

def evaluate_request(request, rules, platform="posix"):
    results=[]; any_ask=False
    for pattern in request["patterns"]:
        result=evaluate_pattern(request["permission"],pattern,rules,platform)
        results.append({"pattern":pattern,**result})
        if result["action"]=="deny":
            return {"action":"deny","patterns":results}
        any_ask |= result["action"]=="ask"
    return {"action":"ask" if any_ask else "allow","patterns":results}

def evaluate_case(case, rules, platform="posix"):
    if case["scope"]=="broker_contract_non_native":
        return {"action":"excluded","requests":[]}
    results=[]; any_ask=False
    for request in case["native_requests"]:
        result=evaluate_request(request,rules,platform)
        results.append({"permission":request["permission"],**result})
        if result["action"]=="deny":
            return {"action":"deny","requests":results}
        any_ask |= result["action"]=="ask"
    return {"action":"ask" if any_ask else "allow","requests":results}

def summarize(policy, projection, platform="posix"):
    rules=expand_rules(policy)
    cases=expand_cases(projection)
    rows=[]
    for case in cases:
        result=evaluate_case(case,rules,platform)
        rows.append({
            "id":case["id"],"safety_expectation":case["safety_expectation"],
            "candidate_decision":result["action"],"scope":case["scope"],
            "note":case["note"],"details":result,
        })
    native=[r for r in rows if r["candidate_decision"]!="excluded"]
    counts={a:sum(r["candidate_decision"]==a for r in native) for a in ("allow","ask","deny")}
    by_id={c["id"]:c for c in cases}
    expected_allow=sum(r["safety_expectation"]=="allow" for r in native)
    summary={
        "source_total":len(rows),"native_scope":len(native),
        "excluded_non_native":len(rows)-len(native),"candidate_counts":counts,
        "auto_allow_rate_native":counts["allow"]/len(native),
        "ask_rate_native":counts["ask"]/len(native),
        "safe_allow_capture":sum(
            r["candidate_decision"]=="allow" and r["safety_expectation"]=="allow"
            for r in native
        )/expected_allow,
        "unsafe_auto_allow":sum(
            r["candidate_decision"]=="allow" and r["safety_expectation"]!="allow"
            for r in native
        ),
        "dangerous_false_safe":sum(
            r["candidate_decision"]=="allow" and r["safety_expectation"]=="deny"
            for r in native
        ),
        "expected_deny_but_native_ask":sum(
            r["candidate_decision"]=="ask" and r["safety_expectation"]=="deny"
            for r in native
        ),
        "expected_allow_but_native_ask":sum(
            r["candidate_decision"]=="ask" and r["safety_expectation"]=="allow"
            for r in native
        ),
        "expected_ask_promoted_to_allow":sum(
            r["candidate_decision"]=="allow" and r["safety_expectation"]=="ask"
            for r in native
        ),
        "wrapper_false_safe":sum(
            r["candidate_decision"]=="allow" and "wrapper" in by_id[r["id"]]["tags"]
            for r in native
        ),
        "unknown_false_safe":sum(
            r["candidate_decision"]=="allow" and "unknown" in by_id[r["id"]]["tags"]
            for r in native
        ),
        "secret_false_safe":sum(
            r["candidate_decision"]=="allow" and "secret" in by_id[r["id"]]["tags"]
            for r in native
        ),
    }
    return {"summary":summary,"cases":rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("policy"); p.add_argument("projection")
    p.add_argument("--platform",choices=["posix","win32"],default="posix")
    p.add_argument("--json-out")
    a=p.parse_args()
    policy=json.loads(Path(a.policy).read_text(encoding="utf-8"))
    projection=json.loads(Path(a.projection).read_text(encoding="utf-8"))
    output=summarize(policy,projection,a.platform)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(output["summary"],ensure_ascii=False,indent=2))
    keys=("unsafe_auto_allow","dangerous_false_safe","wrapper_false_safe","unknown_false_safe","secret_false_safe")
    return 0 if all(output["summary"][k]==0 for k in keys) else 1

if __name__=="__main__":
    raise SystemExit(main())

"""Canonical policy execution and the real Ledger; no cloud or actor probes."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "runtime"))
from approval_owner.ledger import Ledger, Refusal
from test_yc_snapshot_read import context
from yc_owner_native_veto import NativeVeto
from yc_snapshot_read import ReadError, ReadProfile, dispatch_read


def source(native=None, yc=None):
    native = native or json.loads((ROOT / "policy/native/rules.v1.json").read_bytes())
    yc = yc or json.loads((ROOT / "policy/yc/yc_policy.v1.json").read_bytes())
    a, b = (json.dumps(v).encode() for v in (native, yc))
    return NativeVeto(a, b, native_sha256=hashlib.sha256(a).hexdigest(), yc_sha256=hashlib.sha256(b).hexdigest())


class NativeVetoTests(unittest.TestCase):
    def test_exact_current_sources_are_not_constant_ask(self):
        native = json.loads((ROOT / "policy/native/rules.v1.json").read_bytes())
        for action in ("allow", "ask", "deny"):
            current = json.loads(json.dumps(native))
            current["rules"].append(["yc.exact.owner", "bash", "*compute snapshot get --id synthetic-snapshot*", action])
            veto = source(current)
            ctx = replace(context("windows"), policy_revision=veto.revision)
            # Other two reads remain ask. One deny is terminal for all three.
            self.assertEqual(veto.check(ctx), "deny" if action == "deny" else "ask")

    def test_logical_and_resolved_path_denies_are_both_terminal(self):
        for pattern in ("yc compute disk get *", "C:/fixture/yc.exe compute instance get *"):
            native = json.loads((ROOT / "policy/native/rules.v1.json").read_bytes())
            native["rules"].append(["owner.additional.deny", "bash", pattern, "deny"])
            veto = source(native)
            self.assertEqual(veto.check(replace(context("windows"), policy_revision=veto.revision)), "deny")

    def test_existing_yc_hard_veto_is_shared_and_precedes_any_allow(self):
        native = json.loads((ROOT / "policy/native/rules.v1.json").read_bytes())
        native["rules"].append(["yc.allow", "bash", "*", "allow"])
        yc = json.loads((ROOT / "policy/yc/yc_policy.v1.json").read_bytes())
        yc["deny"]["sequences"].append(["compute", "snapshot", "get"])
        veto = source(native, yc)
        self.assertEqual(veto.check(replace(context("windows"), policy_revision=veto.revision)), "deny")

    def test_hash_mismatch_duplicate_keys_and_unknown_semantics_are_refused(self):
        yc = (ROOT / "policy/yc/yc_policy.v1.json").read_bytes()
        valid = (ROOT / "policy/native/rules.v1.json").read_bytes()
        unsupported = json.loads(valid)
        unsupported["target"]["permission_semantics"] = "unknown"
        for raw, pin in ((valid, "0" * 64), (b'{"schema":1,"schema":1}', None),
                         (json.dumps(unsupported).encode(), None)):
            with self.subTest(raw=raw[:20]), self.assertRaises(ReadError):
                NativeVeto(raw, yc, native_sha256=pin or hashlib.sha256(raw).hexdigest(),
                           yc_sha256=hashlib.sha256(yc).hexdigest())

    def test_revision_change_burns_existing_once_before_spawn(self):
        veto = source()
        ctx = replace(context("windows"), policy_revision=veto.revision)
        profile = ReadProfile(lambda: ctx, lambda c: veto.check(c))
        ledger = Ledger("owner", ["agent"], ctx.policy_revision, ctx.execution_host_id,
                        canonicalizer=profile.canonicalize, consume_check=profile.check_consumption)
        view = ledger.handle("agent", "agent", {"action": "propose", "operation": profile.operation()})
        bound = {k: view[k] for k in ("request_id", "operation_sha256")}
        ledger.handle("decision", "owner", {"action": "decide", **bound, "decision": "approve"})
        native = json.loads((ROOT / "policy/native/rules.v1.json").read_bytes())
        native["rules"].append(["owner.new.deny", "bash", "yc compute *", "deny"])
        original, veto = veto, source(native)
        starts = []
        with self.assertRaisesRegex(Refusal, "CONSUME_CONTEXT_CHANGED"):
            dispatch_read(ledger, "agent", {"action": "consume", **bound}, profile=profile,
                          start=lambda *args: starts.append(args))
        veto = original
        with self.assertRaisesRegex(Refusal, "APPROVAL_REQUIRED"):
            dispatch_read(ledger, "agent", {"action": "consume", **bound}, profile=profile,
                          start=lambda *args: starts.append(args))
        self.assertEqual(starts, [])

    def test_allow_does_not_grant_or_accept_an_agent_decision(self):
        native = json.loads((ROOT / "policy/native/rules.v1.json").read_bytes())
        native["rules"].append(["yc.allow", "bash", "*", "allow"])
        veto = source(native)
        ctx = replace(context("windows"), policy_revision=veto.revision)
        self.assertEqual(veto.check(ctx), "allow")
        profile = ReadProfile(lambda: ctx, veto.check)
        ledger = Ledger("owner", ["agent"], ctx.policy_revision, ctx.execution_host_id,
                        canonicalizer=profile.canonicalize, consume_check=profile.check_consumption)
        view = ledger.handle("agent", "agent", {"action": "propose", "operation": profile.operation()})
        bound = {k: view[k] for k in ("request_id", "operation_sha256")}
        with self.assertRaisesRegex(Refusal, "APPROVAL_REQUIRED"):
            ledger.handle("agent", "agent", {"action": "consume", **bound})
        with self.assertRaisesRegex(Refusal, "AGENT_CANNOT_DECIDE"):
            ledger.handle("agent", "agent", {"action": "decide", **bound, "decision": "approve"})


if __name__ == "__main__":
    unittest.main()

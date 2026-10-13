#!/usr/bin/env python3
"""Q1: exact native question lifecycle; all replies are synthetic, not grants."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

VERSION = "1.19.0"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
QUESTIONS = [
    {"header": f"Choice {i}", "question": f"Choose synthetic option {i}",
     "options": [{"label": f"A{i}", "description": "First fixture option"},
                 {"label": f"B{i}", "description": "Second fixture option"}]}
    for i in range(1, 4)
]
ANSWERS = [["A1"], ["B2"], ["A3"]]
SENTINEL = "Q1_MUST_NOT_EXECUTE"


class Inconclusive(RuntimeError):
    """Missing observation must never be reported as success."""


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(method, base, route, directory, payload=None, timeout=10):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + route, data=data, method=method,
        headers={"x-opencode-directory": directory, "content-type": "application/json"})
    with OPENER.open(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def parts(messages, tool=None):
    return [p for m in messages for p in m.get("parts", [])
            if p.get("type") == "tool" and (tool is None or p.get("tool") == tool)]


def event_line(raw):
    # SSE permits both 'data: {...}' and 'data:{...}'.
    if not raw.startswith(b"data:"):
        return None
    event = json.loads(raw[5:].strip())
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise Inconclusive("unrecognized event format")
    return event


def guard_request(request, session_id, expected_call, expected_questions, messages):
    """Controller check, not a claim about native HTTP authentication."""
    tool = request.get("tool") or {}
    if request.get("sessionID") != session_id or tool.get("callID") != expected_call:
        raise Inconclusive("request session/call correlation mismatch")
    if not isinstance(request.get("id"), str) or not request["id"].startswith("que"):
        raise Inconclusive("request identity missing")
    # Native Request may add 'custom'; compare the expected prompt fields only.
    actual = [{key: q.get(key) for key in expected_questions[i]}
              for i, q in enumerate(request.get("questions", []))
              if i < len(expected_questions)]
    if len(request.get("questions", [])) != len(expected_questions) or actual != expected_questions:
        raise Inconclusive("question contents mismatch")
    matches = [p for p in parts(messages, "question") if p.get("callID") == expected_call
               and p.get("messageID") == tool.get("messageID")
               and p.get("sessionID") == session_id]
    if len(matches) != 1 or (matches[0].get("state") or {}).get("status") != "running":
        raise Inconclusive("request not bound to one running native tool")
    if matches[0]["state"].get("input", {}).get("questions") != expected_questions:
        raise Inconclusive("persisted question input mismatch")


def guard_answers(answers, expected):
    if not isinstance(answers, list) or len(answers) != len(expected):
        raise ValueError("answer count mismatch")
    if answers != expected:
        raise ValueError("synthetic answer/order mismatch")


class Observer:
    def __init__(self, base, directory):
        self.base, self.directory = base, directory
        self.events = []
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.failed = False
        self.stopping = False
        self.response = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            request = urllib.request.Request(self.base + "/event",
                headers={"x-opencode-directory": self.directory, "accept": "text/event-stream"})
            with OPENER.open(request, timeout=90) as response:
                self.response = response
                for raw in response:
                    if self.stopping:
                        break
                    event = event_line(raw)
                    if event is None:
                        continue
                    with self.lock:
                        self.events.append(event)
                    if event["type"] == "server.connected":
                        self.ready.set()
                if not self.stopping:
                    self.failed = True
        except Exception:
            if not self.stopping:
                self.failed = True
            self.ready.set()

    def start(self):
        self.thread.start()
        if not self.ready.wait(15) or self.failed:
            raise Inconclusive("event subscription not established")

    def snapshot(self):
        with self.lock:
            return deepcopy(self.events)

    def close(self):
        # The server is terminated by the fixture first, unblocking the reader.
        self.stopping = True
        self.thread.join(timeout=5)


def evaluate(events, messages, session_id, groups, outcome, complete):
    """Cross-check the live stream against persisted native tool states."""
    if not complete:
        raise Inconclusive("observation incomplete")
    relevant = [e for e in events if e.get("properties", {}).get("sessionID") == session_id]
    if any(e["type"] == "session.error" for e in relevant) and outcome not in {"reject", "cancel", "ask"}:
        raise AssertionError("native session error")
    asked = [e["properties"] for e in relevant if e["type"] == "question.asked"]
    replied = [e["properties"] for e in relevant if e["type"] == "question.replied"]
    rejected = [e["properties"] for e in relevant if e["type"] == "question.rejected"]
    qparts = parts(messages, "question")
    wanted = len(groups)
    if len(qparts) != wanted:
        raise AssertionError("unexpected native question tool count")
    if len(asked) < wanted:
        raise Inconclusive("asked event missing")
    if len(asked) != wanted or len({e["id"] for e in asked}) != wanted:
        raise AssertionError("duplicate/extra question request")
    if len({e.get("tool", {}).get("callID") for e in asked}) != wanted:
        raise AssertionError("duplicate question call")
    for index, group in enumerate(groups):
        req = asked[index]
        call = f"call_q1_{index}"
        if req.get("tool", {}).get("callID") != call:
            raise Inconclusive("event call correlation lost")
        candidates = [p for p in qparts if p.get("callID") == call]
        if len(candidates) != 1:
            raise Inconclusive("persisted call correlation lost")
        p = candidates[0]
        if (p.get("sessionID") != session_id or
                p.get("messageID") != req.get("tool", {}).get("messageID")):
            raise Inconclusive("persisted message/session correlation lost")
        if p.get("state", {}).get("input", {}).get("questions") != group:
            raise AssertionError("native tool inputs changed")
    if outcome in {"reply", "deny", "ask"}:
        if len(replied) < wanted:
            raise Inconclusive("reply event missing")
        if len(replied) != wanted or rejected:
            raise AssertionError("unexpected reply/rejection lifecycle")
        for index, group in enumerate(groups):
            expected = ANSWERS if len(group) == 3 else [ANSWERS[index]]
            answer = next((e for e in replied if e.get("requestID") == asked[index]["id"]), None)
            if answer is None:
                raise Inconclusive("reply request correlation lost")
            if answer.get("answers") != expected:
                raise AssertionError("native reply answers changed")
            state = next(p["state"] for p in qparts if p.get("callID") == f"call_q1_{index}")
            if state.get("status") != "completed" or state.get("metadata", {}).get("answers") != expected:
                raise AssertionError("native completed answers changed")
    elif outcome == "reject":
        if len(rejected) != wanted or replied:
            raise Inconclusive("rejection lifecycle not observed")
        if {e.get("requestID") for e in rejected} != {e["id"] for e in asked}:
            raise Inconclusive("rejection correlation lost")
        if any(p["state"].get("status") != "error" for p in qparts):
            raise AssertionError("rejected question completed")
    elif outcome == "cancel":
        if replied or any(p["state"].get("status") == "completed" for p in qparts):
            raise AssertionError("cancel produced fictitious answer")
        if any(p["state"].get("status") != "error" for p in qparts):
            raise Inconclusive("cancel tool termination not observed")
    elif outcome == "none":
        if qparts or asked or replied or rejected:
            raise AssertionError("known decisions caused extra question")
    else:
        raise AssertionError("unknown fixture outcome")
    permission = [e for e in relevant if e["type"] == "permission.asked"]
    bash = parts(messages, "bash")
    if outcome in {"deny", "ask"} and len(bash) == 1:
        if (bash[0].get("callID") != "call_q1_shell" or
                bash[0].get("state", {}).get("input", {}).get("command") != f"echo {SENTINEL}"):
            raise AssertionError("technical operation binding changed")
    if outcome == "deny":
        if len(bash) != 1 or bash[0]["state"].get("status") != "error" or permission:
            raise AssertionError("question answer weakened hard DENY")
    elif outcome == "ask":
        if len(bash) != 1 or bash[0]["state"].get("status") != "error" or len(permission) != 1:
            raise AssertionError("question answer unexpectedly resolved technical ASK")
        denied = [e["properties"] for e in relevant if e["type"] == "permission.replied"]
        if len(denied) != 1 or denied[0].get("requestID") != permission[0]["properties"].get("id"):
            raise Inconclusive("technical rejection correlation lost")
        if denied[0].get("reply") != "reject":
            raise AssertionError("technical ASK granted unexpectedly")
    elif bash or permission:
        raise AssertionError("unexpected permission or shell operation")
    if any(p.get("state", {}).get("status") == "completed" for p in bash):
        raise AssertionError("denied/pending shell executed")
    return {"question_request_count": len(asked),
            "question_item_count": sum(len(e["questions"]) for e in asked),
            "permission_request_count": len(permission),
            "user_interruption_count": None,
            "request_interruption_surrogate": len(asked) + len(permission),
            "unsafe_automatic_allow": 0, "hard_deny_bypass_count": 0}


@contextmanager
def provider(groups, shell_after=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
            names = {t.get("function", {}).get("name") for t in body.get("tools", [])}
            count = len([m for m in body.get("messages", []) if m.get("role") == "tool"])
            index = count
            if index < len(groups):
                name, args, call = "question", {"questions": groups[index]}, f"call_q1_{index}"
            elif shell_after and index == len(groups):
                name, args, call = "bash", {"command": f"echo {SENTINEL}"}, "call_q1_shell"
            else:
                name = None
            # Background title/summary requests carry no tools and are not scenarios.
            if not names:
                name = None
            if name and name not in names:
                self.send_error(400, "required native tool unavailable")
                return
            delta = {"role": "assistant", "content": "Q1_CONTINUED"}
            if name:
                delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": call,
                    "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for d, finish in [(delta, None), ({}, "tool_calls" if name else "stop")]:
                chunk = {"id": f"chatcmpl-q1-{index}", "object": "chat.completion.chunk",
                         "created": 1, "model": "mock", "choices": [{"index": 0, "delta": d, "finish_reason": finish}]}
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_scenario(binary, name):
    groups = [[q] for q in QUESTIONS] if name == "sequential" else [] if name == "known" else [QUESTIONS]
    outcome = {"rejected": "reject", "cancelled": "cancel", "native_abort": "cancel", "known": "none",
               "question_not_grant_deny": "deny", "question_not_grant_ask": "ask"}.get(name, "reply")
    with tempfile.TemporaryDirectory(prefix="q1-") as tmp, provider(groups, outcome in {"deny", "ask"}) as model_port:
        root = Path(tmp)
        project, home = root / "project", root / "home"
        project.mkdir()
        home.mkdir()
        config = {"$schema": "https://opencode.ai/config.json", "snapshot": False,
            "permission": {"bash": {"*": "ask", f"echo {SENTINEL}": "ask" if outcome == "ask" else "deny"}},
            "provider": {"q1": {"name": "Q1 Local Fixture", "npm": "@ai-sdk/openai-compatible",
                "api": f"http://127.0.0.1:{model_port}/v1", "models": {"mock": {
                    "name": "Mock", "tool_call": True, "limit": {"context": 32000, "output": 4096}}},
                "options": {"apiKey": "synthetic-local-test", "baseURL": f"http://127.0.0.1:{model_port}/v1"}}}}
        (project / "opencode.json").write_text(json.dumps(config), encoding="utf-8")
        # Do not inherit providers, credentials, plugins, or overriding OpenCode flags.
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "TMP", "TEMP", "TMPDIR"}}
        env.update({"HOME": str(home), "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".local" / "state"),
            "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_CLIENT": "cli"})
        base = f"http://127.0.0.1:{port()}"
        log = (root / "server.log").open("w", encoding="utf-8")
        process = subprocess.Popen([binary, "serve", "--hostname", "127.0.0.1", "--port", base.rsplit(":", 1)[1]],
            cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT)
        observer = Observer(base, str(project))
        try:
            deadline = time.monotonic() + 40
            while True:
                if process.poll() is not None:
                    raise Inconclusive("test server exited before readiness")
                try:
                    http("GET", base, "/session", str(project), timeout=2)
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise Inconclusive("test server not ready")
                    time.sleep(.2)
            observer.start()
            session = http("POST", base, "/session", str(project), {"title": "Q1 fixture"})
            session_id = session["id"]
            foreign = http("POST", base, "/session", str(project), {"title": "Q1 foreign fixture"})["id"]
            http("POST", base, f"/session/{session_id}/prompt_async", str(project), {
                "agent": "build", "model": {"providerID": "q1", "modelID": "mock"},
                "parts": [{"type": "text", "text": "Run the synthetic Q1 scenario."}]})
            answered, tested_guards, aborted, technical_rejected = set(), 0, False, False
            deadline = time.monotonic() + 70
            messages = []
            while time.monotonic() < deadline:
                if observer.failed:
                    raise Inconclusive("event stream disconnected")
                messages = http("GET", base, f"/session/{session_id}/message", str(project))
                pending = http("GET", base, "/question", str(project))
                for req in pending:
                    if req.get("sessionID") != session_id or req["id"] in answered:
                        continue
                    observed = [e.get("properties", {}) for e in observer.snapshot()
                                if e["type"] == "question.asked" and e.get("properties", {}).get("id") == req["id"]]
                    if not observed:
                        continue
                    if len(observed) != 1 or any(observed[0].get(k) != req.get(k)
                                                for k in ("id", "sessionID", "tool", "questions")):
                        raise Inconclusive("pending request differs from observed event")
                    index = len(answered)
                    if index >= len(groups):
                        raise AssertionError("extra pending question")
                    # The session snapshot above can precede the next question event.
                    # Refresh read-only evidence; never reply using that stale snapshot.
                    messages = http("GET", base, f"/session/{session_id}/message", str(project))
                    bound = [p for p in parts(messages, "question")
                             if p.get("callID") == req.get("tool", {}).get("callID")
                             and p.get("messageID") == req.get("tool", {}).get("messageID")]
                    if not bound:
                        continue
                    guard_request(req, session_id, f"call_q1_{index}", groups[index], messages)
                    expected = ANSWERS if len(groups[index]) == 3 else [ANSWERS[index]]
                    if name == "controller_guards":
                        # Reject stale identity/foreign session before any reply mutation.
                        for wrong in [foreign, "ses_unknown"]:
                            try:
                                guard_request(req, wrong, f"call_q1_{index}", groups[index], messages)
                            except Inconclusive:
                                tested_guards += 1
                            else:
                                raise AssertionError("foreign correlation accepted")
                        for invalid in [[], list(reversed(expected)), expected + [["extra"]]]:
                            try:
                                guard_answers(invalid, expected)
                            except ValueError:
                                tested_guards += 1
                            else:
                                raise AssertionError("invalid synthetic reply accepted")
                        if not any(q["id"] == req["id"] for q in http("GET", base, "/question", str(project))):
                            raise AssertionError("controller guards mutated pending state")
                    if outcome == "cancel":
                        if name == "cancelled":
                            # Abort alone leaves a stale pending question in exact 1.19.0.
                            # Close this correlated request explicitly before aborting.
                            http("POST", base, f"/question/{req['id']}/reject", str(project))
                        http("POST", base, f"/session/{session_id}/abort", str(project))
                        aborted = True
                    elif outcome == "reject":
                        http("POST", base, f"/question/{req['id']}/reject", str(project))
                    else:
                        guard_answers(expected, expected)
                        http("POST", base, f"/question/{req['id']}/reply", str(project), {"answers": expected})
                    answered.add(req["id"])
                if outcome == "ask":
                    requests = http("GET", base, "/permission", str(project))
                    for req in requests:
                        if req.get("sessionID") != session_id:
                            continue
                        if req.get("permission") != "bash" or req.get("tool", {}).get("callID") != "call_q1_shell":
                            raise Inconclusive("technical permission correlation lost")
                        if req.get("metadata", {}).get("command") != f"echo {SENTINEL}":
                            raise Inconclusive("technical permission command changed")
                        if any(p.get("state", {}).get("status") == "completed" for p in parts(messages, "bash")):
                            raise AssertionError("Q reply automatically executed pending ASK")
                        http("POST", base, f"/permission/{req['id']}/reply", str(project), {"reply": "reject"})
                        technical_rejected = True
                ev = observer.snapshot()
                idle = any(e.get("properties", {}).get("sessionID") == session_id and (
                    e["type"] == "session.idle" or (e["type"] == "session.status" and
                    e.get("properties", {}).get("status", {}).get("type") == "idle")) for e in ev)
                text_done = any(p.get("type") == "text" and "Q1_CONTINUED" in p.get("text", "")
                                for m in messages for p in m.get("parts", []))
                ended_tools = all(p.get("state", {}).get("status") in {"completed", "error"} for p in parts(messages))
                terminal_without_continuation = aborted or outcome == "reject" or technical_rejected
                if idle and ended_tools and (text_done or terminal_without_continuation) and (outcome != "ask" or technical_rejected):
                    break
                time.sleep(.1)
            else:
                summary = {"tool_states": [p.get("state", {}).get("status") for p in parts(messages)],
                           "event_types": sorted({e["type"] for e in observer.snapshot()}),
                           "controller_replies": len(answered), "technical_rejected": technical_rejected}
                raise Inconclusive("native scenario timed out: " + json.dumps(summary))
            remaining = http("GET", base, "/question", str(project))
            retained = any(q.get("sessionID") == session_id for q in remaining)
            if retained and name != "native_abort":
                raise AssertionError("terminal session retained pending question")
            late_reply_blocked = None
            if name == "native_abort" and retained:
                stale = next(q for q in remaining if q.get("sessionID") == session_id)
                try:
                    guard_request(stale, session_id, "call_q1_0", groups[0], messages)
                except Inconclusive:
                    late_reply_blocked = True
                else:
                    raise AssertionError("controller accepted reply to aborted native tool")
            ev = observer.snapshot()
            metrics = evaluate(ev, messages, session_id, groups, outcome, not observer.failed)
            # Mutation controls: dropping observations cannot pass; duplicating request must fail.
            missing = [e for e in ev if e["type"] != "question.asked"]
            if groups:
                try:
                    evaluate(missing, messages, session_id, groups, outcome, True)
                except Inconclusive:
                    pass
                else:
                    raise AssertionError("missing events produced false success")
                injected = ev + [next(e for e in ev if e["type"] == "question.asked")]
                try:
                    evaluate(injected, messages, session_id, groups, outcome, True)
                except AssertionError:
                    pass
                else:
                    raise AssertionError("injected duplicate produced false success")
            return {"scenario": name, "status": "OBSERVED_GAP" if name == "native_abort" and retained else "PASS",
                    "metrics": metrics, "pending_question_after_abort": retained if name == "native_abort" else False,
                    "late_reply_controller_blocked": late_reply_blocked,
                    "controller_guard_rejections": tested_guards, "actual_human_ui_proof": False}
        finally:
            observer.stopping = True
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            observer.close()
            log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    binary = str(Path(args.opencode).resolve())
    version = subprocess.run([binary, "--version"], check=True, capture_output=True, text=True, timeout=20).stdout.strip()
    if version != VERSION:
        raise SystemExit(f"Expected exact OpenCode {VERSION}")
    results = []
    for name in ["batched", "sequential", "known", "rejected", "cancelled", "native_abort", "controller_guards",
                 "question_not_grant_deny", "question_not_grant_ask"]:
        try:
            result = run_scenario(binary, name)
        except Inconclusive as exc:
            result = {"scenario": name, "status": "INCONCLUSIVE", "reason": str(exc)}
        except AssertionError as exc:
            result = {"scenario": name, "status": "FAIL", "reason": str(exc)}
        except Exception as exc:
            # Never publish response bodies, credentials, local paths or raw server logs.
            result = {"scenario": name, "status": "INCONCLUSIVE", "reason": type(exc).__name__}
        results.append(result)
        print(json.dumps(result), flush=True)
    ok = all(r["status"] == "PASS" or (r["scenario"] == "native_abort" and r["status"] == "OBSERVED_GAP") for r in results)
    known_gap = any(r["status"] == "OBSERVED_GAP" for r in results)
    native_cleanup = any(r["scenario"] == "native_abort" and r["status"] == "PASS"
                         and r.get("pending_question_after_abort") is False for r in results)
    comparison = None
    if ok:
        batch, sequential = results[:2]
        if (batch["metrics"]["question_request_count"], sequential["metrics"]["question_request_count"]) != (1, 3):
            ok = False
        if (batch["metrics"]["question_item_count"], sequential["metrics"]["question_item_count"]) != (3, 3):
            ok = False
        comparison = {"question_items_each": 3, "batched_requests": 1, "sequential_requests": 3,
                      "real_user_interruptions_measured": False}
    report = {"schema": "opencode-question-q1/v1", "opencode_version": version,
              "platform": os.name, "status": "PASS_WITH_KNOWN_GAP" if ok and known_gap else "PASS" if ok else "FAIL",
              "scope": "synthetic_question_only", "native_abort_cleanup_proven": native_cleanup,
              "compatibility_deployable": False, "actual_human_ui_proof": False,
              "comparison": comparison, "results": results}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

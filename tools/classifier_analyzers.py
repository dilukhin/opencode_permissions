#!/usr/bin/env python3
"""Bounded deterministic analyzers over exact parsed/preflight facts (DC-2).

No raw shell parsing occurs here. Inputs must be parsed-simple/v1 facts produced by
an exact parser/preflight adapter. DC-4 will prove the real OpenCode adapter.
"""
from __future__ import annotations

import copy
from typing import Any, Iterable

from classifier_core import (
    ClassifierError,
    allow_result,
    ask_result,
    compose_results,
    deny_result,
)
from normalized_operation_identity import jcs_dumps

FACT_SCHEMA = "parsed-simple/v1"
EXACT_PARSER_STATUS = "exact"
INTERPRETERS = {"bash", "sh", "python", "python3", "node", "powershell", "pwsh", "cmd"}
ARBITRARY_CODE_TOOLS = {"cmake", "ctest"}


def _valid_path_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("lexical"), str)
        and bool(value["lexical"])
        and isinstance(value.get("object_identity"), str)
        and bool(value["object_identity"])
        and value.get("follow_mode") in {"target", "link"}
    )


def _valid_executable(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("invoked"), str)
        and bool(value["invoked"])
        and isinstance(value.get("resolved_path"), str)
        and bool(value["resolved_path"])
        and isinstance(value.get("object_identity"), str)
        and bool(value["object_identity"])
    )


def _target_valid(target: Any) -> bool:
    return (
        isinstance(target, dict)
        and isinstance(target.get("role"), str)
        and bool(target["role"])
        and isinstance(target.get("kind"), str)
        and bool(target["kind"])
        and isinstance(target.get("identity"), dict)
    )


def _targets(fact: dict[str, Any]) -> list[dict[str, Any]]:
    values = fact.get("targets", [])
    if not isinstance(values, list) or not all(_target_valid(item) for item in values):
        return []
    return copy.deepcopy(values)


def _ask_unknown(code: str, *, effects: Iterable[str] = ("unknown",), targets: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    return ask_result(
        reason_codes=[code],
        effects=effects,
        targets=targets,
        uncertainties=[code],
    )


def _base_fact_valid(fact: Any) -> bool:
    return isinstance(fact, dict) and fact.get("schema") == FACT_SCHEMA


def _process_operation(fact: dict[str, Any], effects: Iterable[str], targets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": fact["platform"],
        "channel": "local",
        "operation_kind": "process_exec",
        "execution": {
            "kind": "argv",
            "executable": copy.deepcopy(fact["executable"]),
            "argv": list(fact["argv"]),
            "cwd": copy.deepcopy(fact["cwd"]),
        },
        "targets": copy.deepcopy(list(targets)),
        "effects": sorted(set(effects)),
        "context_dependencies": [],
    }


def _workspace_cwd_target(fact: dict[str, Any]) -> dict[str, Any] | None:
    cwd = fact.get("cwd")
    if not _valid_path_identity(cwd) or cwd.get("boundary") != "workspace":
        return None
    return {"role": "cwd", "kind": "workspace_directory", "identity": copy.deepcopy(cwd)}


def _kind_targets(fact: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [item for item in _targets(fact) if item["kind"] == kind]


def _is_secret(target: dict[str, Any]) -> bool:
    return target["kind"] == "secret_file" or target["identity"].get("sensitivity") == "secret"


def _is_nonsecret_workspace_file(target: dict[str, Any]) -> bool:
    ident = target["identity"]
    return (
        target["kind"] == "workspace_file"
        and _valid_path_identity(ident)
        and ident.get("boundary") == "workspace"
        and ident.get("sensitivity") == "nonsecret"
    )


def _is_workspace_directory(target: dict[str, Any]) -> bool:
    ident = target["identity"]
    return (
        target["kind"] in {"workspace_directory", "repository"}
        and _valid_path_identity(ident)
        and ident.get("boundary") == "workspace"
    )


def _requested(target: dict[str, Any]) -> str | None:
    value = target["identity"].get("requested")
    return value if isinstance(value, str) and value else None


def _redirect_decision(fact: dict[str, Any]) -> dict[str, Any] | None:
    redirects = fact.get("redirects", [])
    if redirects in (None, []):
        return None
    if not isinstance(redirects, list):
        return _ask_unknown("syntax.redirect_unknown")

    all_targets = _targets(fact)
    effects = {"process"}
    for redirect in redirects:
        if not isinstance(redirect, dict):
            return _ask_unknown("syntax.redirect_unknown", targets=all_targets)
        kind = redirect.get("kind")
        target = redirect.get("target")
        if not _target_valid(target):
            return _ask_unknown("target.redirect_unknown", targets=all_targets)
        all_targets.append(copy.deepcopy(target))

        if kind in {"write", "append"}:
            effects.add("write")
            if target["kind"] == "system_path":
                effects.update({"system", "external_directory"})
                return deny_result(
                    reason_codes=["redirect.system_write"],
                    effects=effects,
                    targets=all_targets,
                )
            return ask_result(
                reason_codes=["redirect.controlled_write"],
                effects=effects,
                targets=all_targets,
                uncertainties=["write.approval_required"],
            )

        if kind == "read":
            effects.add("read")
            if _is_secret(target):
                effects.add("secrets")
                return deny_result(
                    reason_codes=["redirect.secret_read"],
                    effects=effects,
                    targets=all_targets,
                )
            return ask_result(
                reason_codes=["redirect.input_unmodeled"],
                effects=effects,
                targets=all_targets,
                uncertainties=["syntax.redirect_input"],
            )

        return _ask_unknown("syntax.redirect_unknown", targets=all_targets)
    return None


def analyze_simple(fact: dict[str, Any]) -> dict[str, Any]:
    if not _base_fact_valid(fact):
        return _ask_unknown("input.invalid_fact_schema")

    parser = fact.get("parser")
    if not isinstance(parser, dict) or parser.get("status") != EXACT_PARSER_STATUS:
        return _ask_unknown("syntax.opaque")

    argv = fact.get("argv")
    executable = fact.get("executable")
    cwd = fact.get("cwd")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        return _ask_unknown("syntax.argv_invalid")
    if not _valid_executable(executable):
        return _ask_unknown("identity.executable_missing")
    if argv[0] != executable["invoked"]:
        return _ask_unknown("identity.argv_executable_mismatch")
    if not _valid_path_identity(cwd):
        return _ask_unknown("identity.cwd_missing")

    redirect_result = _redirect_decision(fact)
    if redirect_result is not None:
        return redirect_result

    name = executable["invoked"]
    targets = _targets(fact)

    if name == "pwd" and argv == ["pwd"]:
        cwd_target = _workspace_cwd_target(fact)
        if cwd_target is None:
            return _ask_unknown("target.cwd_boundary_unknown")
        operation = _process_operation(fact, ["process", "read"], [cwd_target])
        return allow_result(operation, reason_codes=["simple.pwd"])

    if name == "git":
        repositories = [item for item in targets if item["kind"] == "repository" and _is_workspace_directory(item)]
        if not repositories:
            return _ask_unknown("git.repository_identity_missing", targets=targets)

        if argv in (["git", "status"], ["git", "status", "--short"]):
            operation = _process_operation(fact, ["process", "read", "git_read"], repositories)
            return allow_result(operation, reason_codes=["git.status.readonly"])

        if len(argv) == 6 and argv[1:5] == ["diff", "--no-ext-diff", "--no-textconv", "--"]:
            requested_path = argv[5]
            files = [
                item for item in targets
                if _is_nonsecret_workspace_file(item) and _requested(item) == requested_path
            ]
            if len(files) != 1:
                return _ask_unknown("git.diff.target_not_proven", effects=["process", "read", "git_read"], targets=targets)
            operation = _process_operation(
                fact,
                ["process", "read", "git_read"],
                [*repositories, files[0]],
            )
            return allow_result(operation, reason_codes=["git.diff.hardened_readonly"])

        if len(argv) >= 2 and argv[1] == "diff":
            return ask_result(
                reason_codes=["git.diff.transforms_unconstrained"],
                effects=["process", "read", "git_read", "unknown_code_execution"],
                targets=targets,
                uncertainties=["git.diff.transforms_unconstrained"],
            )

        if (len(argv) >= 3 and argv[1:3] == ["reset", "--hard"]) or (
            len(argv) >= 2 and argv[1] == "clean" and any(token in {"-f", "-fd", "-df", "--force"} or (token.startswith("-") and "f" in token[1:]) for token in argv[2:])
        ):
            return deny_result(
                reason_codes=["git.destructive"],
                effects=["process", "git_destructive", "write", "delete"],
                targets=repositories,
            )

        return _ask_unknown("git.operation_unsupported", effects=["process", "unknown"], targets=targets)

    if name == "find":
        if "-delete" in argv:
            return deny_result(
                reason_codes=["find.delete"],
                effects=["process", "read", "search", "delete", "write"],
                targets=targets,
            )
        if any(token in {"-exec", "-execdir", "-ok", "-okdir"} for token in argv):
            return ask_result(
                reason_codes=["find.nested_execution"],
                effects=["process", "read", "search", "nested_execution", "unknown_code_execution"],
                targets=targets,
                uncertainties=["find.nested_execution"],
            )
        if len(argv) == 8 and argv[2:8] == ["-type", "f", "-name", argv[5], "-print",] :
            # unreachable shape guard retained below with exact index checks
            pass
        if (
            len(argv) == 8
            and argv[2] == "-type"
            and argv[3] == "f"
            and argv[4] == "-name"
            and isinstance(argv[5], str)
            and argv[6] == "-print"
        ):
            # len==8 would contain an unexpected trailing token: fail closed below.
            return _ask_unknown("find.shape_unsupported", effects=["process", "read", "search"], targets=targets)
        if (
            len(argv) == 7
            and argv[2] == "-type"
            and argv[3] == "f"
            and argv[4] == "-name"
            and isinstance(argv[5], str)
            and argv[6] == "-print"
        ):
            roots = [item for item in targets if _is_workspace_directory(item) and _requested(item) == argv[1]]
            if len(roots) != 1:
                return _ask_unknown("find.root_not_proven", effects=["process", "read", "search"], targets=targets)
            operation = _process_operation(fact, ["process", "read", "search"], roots)
            return allow_result(operation, reason_codes=["find.readonly_print"])
        return _ask_unknown("find.shape_unsupported", effects=["process", "read", "search"], targets=targets)

    if name == "grep":
        if any(token in {"-r", "-R", "--recursive", "--dereference-recursive"} for token in argv[1:]):
            return ask_result(
                reason_codes=["grep.recursive_boundary_unknown"],
                effects=["process", "read", "search", "unknown"],
                targets=targets,
                uncertainties=["grep.recursive_boundary_unknown"],
            )
        if len(argv) == 3:
            requested_path = argv[2]
            candidates = [item for item in targets if _requested(item) == requested_path]
            if any(_is_secret(item) for item in candidates):
                return deny_result(
                    reason_codes=["grep.secret_file"],
                    effects=["process", "read", "search", "secrets"],
                    targets=candidates,
                )
            files = [item for item in candidates if _is_nonsecret_workspace_file(item)]
            if len(files) == 1:
                operation = _process_operation(fact, ["process", "read", "search"], files)
                return allow_result(operation, reason_codes=["grep.single_nonsecret_file"])
            return _ask_unknown("grep.target_not_proven", effects=["process", "read", "search"], targets=targets)
        stdin = fact.get("stdin", {"kind": "none"})
        if len(argv) == 2 and isinstance(stdin, dict) and stdin.get("kind") == "pipe":
            operation = _process_operation(fact, ["process", "read", "search"], [])
            return allow_result(operation, reason_codes=["grep.pipe_input"])
        return _ask_unknown("grep.shape_unsupported", effects=["process", "read", "search"], targets=targets)

    if name == "touch" and len(argv) == 2:
        requested_path = argv[1]
        candidates = [item for item in targets if _requested(item) == requested_path]
        if any(item["kind"] == "system_path" for item in candidates):
            return deny_result(
                reason_codes=["filesystem.system_write"],
                effects=["process", "write", "system", "external_directory"],
                targets=candidates,
            )
        return ask_result(
            reason_codes=["filesystem.controlled_write"],
            effects=["process", "write"],
            targets=candidates,
            uncertainties=["write.approval_required"],
        )

    if name == "printf":
        operation = _process_operation(fact, ["process"], [])
        return allow_result(operation, reason_codes=["stdio.printf"])

    if name in ARBITRARY_CODE_TOOLS or (
        name in {"python", "python3"} and len(argv) >= 3 and argv[1:3] == ["-m", "pytest"]
    ):
        return ask_result(
            reason_codes=["execution.project_code"],
            effects=["process", "unknown_code_execution"],
            targets=targets,
            uncertainties=["execution.project_code"],
        )

    if name in INTERPRETERS:
        return ask_result(
            reason_codes=["execution.interpreter_opaque"],
            effects=["process", "nested_interpreter", "unknown_code_execution"],
            targets=targets,
            uncertainties=["execution.interpreter_opaque"],
        )

    return _ask_unknown("executable.unknown", effects=["process", "unknown"], targets=targets)


def _unique_targets(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for result in results:
        for target in result["targets"]:
            by_key[jcs_dumps(target)] = copy.deepcopy(target)
    return [by_key[key] for key in sorted(by_key)]


def _effects(results: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({effect for result in results for effect in result["effects"]})


def analyze_compound(children: Iterable[dict[str, Any]], operators: list[str]) -> dict[str, Any]:
    child_results = [analyze_simple(child) for child in children]
    if not child_results:
        return _ask_unknown("composition.empty")
    if any(result["decision"] != "ALLOW" for result in child_results):
        return compose_results(child_results)
    if len(operators) != len(child_results) - 1 or any(op not in {"&&", "||", ";"} for op in operators):
        return compose_results(child_results)
    platforms = {child["platform"] for child in children}
    if len(platforms) != 1:
        return compose_results(child_results)
    parent = {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": next(iter(platforms)),
        "channel": "local",
        "operation_kind": "compound",
        "execution": {
            "kind": "compound",
            "steps": [result["operation_identity"] for result in child_results],
            "operators": list(operators),
        },
        "targets": _unique_targets(child_results),
        "effects": _effects(child_results),
        "context_dependencies": [],
    }
    return compose_results(child_results, parent_operation=parent, reason_code="compound")


def analyze_pipeline(children: Iterable[dict[str, Any]], pipes: list[str]) -> dict[str, Any]:
    child_list = list(children)
    child_results = [analyze_simple(child) for child in child_list]
    if not child_results:
        return _ask_unknown("pipeline.empty")
    if any(result["decision"] != "ALLOW" for result in child_results):
        return compose_results(child_results, reason_code="pipeline")
    if len(pipes) != len(child_results) - 1 or any(op not in {"|", "|&"} for op in pipes):
        return compose_results(child_results, reason_code="pipeline")
    platforms = {child["platform"] for child in child_list}
    if len(platforms) != 1:
        return compose_results(child_results, reason_code="pipeline")
    parent = {
        "schema": "normalized-operation/v1",
        "canonicalization": "op-jcs-v1",
        "platform": next(iter(platforms)),
        "channel": "local",
        "operation_kind": "pipeline",
        "execution": {
            "kind": "pipeline",
            "stages": [result["operation_identity"] for result in child_results],
            "pipes": list(pipes),
        },
        "targets": _unique_targets(child_results),
        "effects": _effects(child_results),
        "context_dependencies": [],
    }
    return compose_results(child_results, parent_operation=parent, reason_code="pipeline")

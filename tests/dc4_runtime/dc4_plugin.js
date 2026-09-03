import fs from "node:fs"
import path from "node:path"
import { spawnSync } from "node:child_process"

const repoRoot = process.env.DC4_REPO_ROOT
const tracePath = process.env.DC4_TRACE
const python = process.env.DC4_PYTHON || "python3"
const scenario = process.env.DC4_SCENARIO || "unknown"
const workspaceRoot = process.env.DC4_WORKSPACE_ROOT
const shell = "/bin/dash"

function trace(event, fields = {}) {
  if (!tracePath) return
  fs.appendFileSync(tracePath, JSON.stringify({ event, scenario, ...fields }) + "\n")
}

function snapshotEnv() {
  return Object.fromEntries(Object.entries(process.env).sort(([a], [b]) => a.localeCompare(b)))
}

function sameEnv(left, right) {
  const a = Object.keys(left).sort()
  const b = Object.keys(right).sort()
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i] || left[a[i]] !== right[b[i]]) return false
  }
  return true
}

function prepare(command, cwd) {
  if (!repoRoot || !workspaceRoot) throw new Error("DC4 proof environment incomplete")
  const program = path.join(repoRoot, "tools", "opencode_dc4_adapter.py")
  const child = spawnSync(
    python,
    [program, "prepare", "--command", command, "--cwd", cwd, "--workspace-root", workspaceRoot, "--shell", shell],
    { encoding: "utf8", env: process.env },
  )
  if (child.status !== 0) throw new Error(`DC4 adapter failed with status ${child.status}`)
  return JSON.parse(child.stdout)
}

function key(sessionID, callID) {
  return `${sessionID}:${callID}`
}

export const DC4ProofPlugin = async ({ client, directory }) => {
  const calls = new Map()

  return {
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return
      const command = output?.args?.command
      if (typeof command !== "string") throw new Error("DC4 missing bash command")
      const cwd = output?.args?.workdir ? path.resolve(directory, output.args.workdir) : directory
      calls.set(key(input.sessionID, input.callID), {
        sessionID: input.sessionID,
        callID: input.callID,
        command,
        cwd,
        env: snapshotEnv(),
        guard: null,
      })
      trace("tool_before", { callID: input.callID })
    },

    event: async ({ event }) => {
      if (event?.type !== "permission.asked") return
      const request = event.properties
      if (request?.permission !== "bash") return
      const callID = request?.tool?.callID
      const state = typeof callID === "string" ? calls.get(key(request.sessionID, callID)) : undefined
      trace("permission_asked", { callID: callID || null })
      if (!state || request?.metadata?.command !== state.command) {
        trace("correlation_reject", { callID: callID || null })
        await client.permission.reply({ requestID: request.id, reply: "reject" })
        return
      }
      try {
        const payload = prepare(state.command, state.cwd)
        const decision = payload?.result?.decision
        trace("classifier_result", {
          callID,
          decision,
          operationIdentity: payload?.result?.operation_identity || null,
        })
        if (decision !== "ALLOW" || !payload.guard) {
          await client.permission.reply({ requestID: request.id, reply: "reject" })
          trace("permission_reply_reject", { callID })
          return
        }
        state.guard = payload.guard
        if (scenario === "classifier_env_drift") process.env.DC4_TEST_DRIFT = "1"
        await client.permission.reply({ requestID: request.id, reply: "once" })
        trace("permission_reply_once", { callID })
      } catch {
        trace("classifier_error", { callID })
        try {
          await client.permission.reply({ requestID: request.id, reply: "reject" })
        } catch {}
      }
    },

    "shell.env": async (input, output) => {
      const callID = input?.callID
      const sessionID = input?.sessionID
      const state =
        typeof callID === "string" && typeof sessionID === "string"
          ? calls.get(key(sessionID, callID))
          : undefined
      if (!state?.guard) {
        trace("shell_env_native_passthrough", { callID: callID || null })
        return
      }
      if (Object.keys(output?.env || {}).length !== 0 || !sameEnv(state.env, snapshotEnv())) {
        trace("shell_env_guard_reject", { callID, reason: "environment_drift" })
        delete process.env.DC4_TEST_DRIFT
        throw new Error("DC4_ENVIRONMENT_DRIFT")
      }
      const fresh = prepare(state.command, state.cwd)
      if (fresh?.result?.decision !== "ALLOW" || JSON.stringify(fresh.guard) !== JSON.stringify(state.guard)) {
        trace("shell_env_guard_reject", { callID, reason: "identity_drift" })
        throw new Error("DC4_IDENTITY_DRIFT")
      }
      trace("shell_env_guard_pass", {
        callID,
        operationIdentity: state.guard.operation_identity,
      })
    },

    "tool.execute.after": async (input, output) => {
      if (input.tool !== "bash") return
      const expected = process.env.DC4_EXPECT_SENTINEL || ""
      trace("tool_after", {
        callID: input.callID,
        outputMatched: expected ? String(output?.output || "").includes(expected) : false,
      })
    },
  }
}

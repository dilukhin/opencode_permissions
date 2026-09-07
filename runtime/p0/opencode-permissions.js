import crypto from "node:crypto"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { spawnSync } from "node:child_process"

const DOMAIN = "opencode_permissions.pilot_artifact.v1\n"
const root = path.dirname(fileURLToPath(import.meta.url))
const manifestPath = path.join(root, "manifest.json")
const profilePath = path.join(root, "profile.json")
const adapterPath = path.join(root, "runtime", "opencode_p0_adapter.py")

function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex")
}

function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stable(value[key])}`).join(",")}}`
  }
  return JSON.stringify(value)
}

function artifactIdentityCore(manifest) {
  return {
    artifact_format: manifest.artifact_format,
    owner: manifest.owner,
    target: manifest.target,
    native_policy_artifact_id: manifest.native_policy_artifact_id,
    classifier_profile: manifest.classifier_profile,
    files: manifest.files,
    constraints: manifest.constraints,
  }
}

function safeBundlePath(relativePath) {
  if (typeof relativePath !== "string" || !relativePath || path.isAbsolute(relativePath)) {
    throw new Error("P0_BUNDLE_INVALID_PATH")
  }
  const full = path.resolve(root, relativePath)
  if (full !== root && !full.startsWith(root + path.sep)) throw new Error("P0_BUNDLE_PATH_ESCAPE")
  return full
}

function verifyBundle() {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"))
  if (manifest?.artifact_format !== "opencode-permissions-pilot-artifact/v1") {
    throw new Error("P0_BUNDLE_FORMAT_UNSUPPORTED")
  }
  if (manifest?.owner !== "dilukhin/opencode_permissions") throw new Error("P0_BUNDLE_OWNER_MISMATCH")
  if (manifest?.status !== "mp0_ready") throw new Error("P0_BUNDLE_NOT_READY")

  const expectedArtifactId = `sha256:${sha256(DOMAIN + stable(artifactIdentityCore(manifest)))}`
  if (manifest.artifact_id !== expectedArtifactId) throw new Error("P0_BUNDLE_ARTIFACT_ID_MISMATCH")
  if (manifest.artifact_path_segment !== `sha256-${expectedArtifactId.slice("sha256:".length)}`) {
    throw new Error("P0_BUNDLE_PATH_SEGMENT_MISMATCH")
  }

  if (!Array.isArray(manifest.files) || manifest.files.length === 0) throw new Error("P0_BUNDLE_FILES_MISSING")
  for (const item of manifest.files) {
    const full = safeBundlePath(item.path)
    const actual = sha256(fs.readFileSync(full))
    if (actual !== item.sha256) throw new Error("P0_BUNDLE_FILE_DIGEST_MISMATCH")
  }

  const constraints = manifest.constraints || {}
  if (
    constraints.exact_version_only !== true ||
    constraints.nearest_version_fallback !== false ||
    constraints.auditor_enabled !== false ||
    constraints.workspace_trust_enabled !== false ||
    constraints.state_changing_classifier_enabled !== false ||
    constraints.developer_checkout_dependency !== false
  ) {
    throw new Error("P0_BUNDLE_CONSTRAINT_MISMATCH")
  }

  const profile = JSON.parse(fs.readFileSync(profilePath, "utf8"))
  if (profile?.classifier_profile_id !== manifest?.classifier_profile?.id) {
    throw new Error("P0_PROFILE_ID_MISMATCH")
  }
  if (profile?.target?.opencode_version !== manifest?.target?.exact_version) {
    throw new Error("P0_PROFILE_VERSION_MISMATCH")
  }
  if (profile?.target?.compatibility_profile_id !== manifest?.target?.compatibility_profile_id) {
    throw new Error("P0_PROFILE_COMPATIBILITY_MISMATCH")
  }
  if (profile?.target?.native_policy_artifact_id !== manifest?.native_policy_artifact_id) {
    throw new Error("P0_PROFILE_NATIVE_ARTIFACT_MISMATCH")
  }
  return { manifest, profile }
}

function runAdapter(bundle, action, args, guard = null) {
  const python = bundle.profile?.python_runtime?.path
  if (typeof python !== "string" || !path.isAbsolute(python)) throw new Error("P0_PYTHON_RUNTIME_INVALID")
  const command = [
    adapterPath,
    action,
    ...args,
    "--profile",
    profilePath,
  ]
  const child = spawnSync(python, command, {
    encoding: "utf8",
    env: { PYTHONUTF8: "1" },
    cwd: root,
    input: guard ? JSON.stringify(guard) : undefined,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 10_000,
    maxBuffer: 1024 * 1024,
  })
  if (child.status !== 0 || child.error) throw new Error("P0_ADAPTER_PROCESS_FAILED")
  return JSON.parse(child.stdout)
}

function key(sessionID, callID) {
  return `${sessionID}:${callID}`
}

async function runtimeVersion(client) {
  const health = await client.global.health()
  return health?.data?.version ?? null
}

export const OpenCodePermissionsP0 = async ({ client, directory }) => {
  const bundle = verifyBundle()
  const calls = new Map()
  const maxCalls = 1024
  let configuredShell = null
  let configSeen = false
  let versionPromise = null

  async function exactRuntimeReady() {
    if (process.platform !== "linux" || !configSeen) return false
    if (configuredShell !== bundle.profile.shell.path) return false
    if (!versionPromise) versionPromise = runtimeVersion(client).catch(() => null)
    const version = await versionPromise
    return version === bundle.manifest.target.exact_version
  }

  async function reply(request, response) {
    const result = await client.postSessionIdPermissionsPermissionId({
      path: { id: request.sessionID, permissionID: request.id },
      body: { response },
      query: { directory },
    })
    if (result?.error) throw new Error("P0_PERMISSION_REPLY_FAILED")
  }

  return {
    config: async (config) => {
      configSeen = true
      configuredShell = typeof config?.shell === "string" ? config.shell : null
    },

    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return
      const command = output?.args?.command
      if (typeof command !== "string") throw new Error("P0_BASH_COMMAND_MISSING")
      const cwd = output?.args?.workdir ? path.resolve(directory, output.args.workdir) : directory
      if (calls.size >= maxCalls) calls.delete(calls.keys().next().value)
      calls.set(key(input.sessionID, input.callID), {
        sessionID: input.sessionID,
        callID: input.callID,
        command,
        cwd,
        guard: null,
      })
    },

    event: async ({ event }) => {
      if (event?.type !== "permission.asked") return
      const request = event.properties
      if (request?.permission !== "bash") return
      const callID = request?.tool?.callID
      const state = typeof callID === "string" ? calls.get(key(request.sessionID, callID)) : undefined

      if (!state || request?.metadata?.command !== state.command) {
        if (state) calls.delete(key(request.sessionID, callID))
        await reply(request, "reject")
        return
      }

      if (!(await exactRuntimeReady())) return

      let payload
      try {
        payload = runAdapter(
          bundle,
          "prepare",
          ["--command", state.command, "--cwd", state.cwd, "--workspace-root", directory],
        )
      } catch {
        return
      }

      const decision = payload?.result?.decision
      if (decision === "DENY") {
        calls.delete(key(request.sessionID, callID))
        await reply(request, "reject")
        return
      }
      if (decision !== "ALLOW" || !payload?.guard) return

      state.guard = payload.guard
      try {
        await reply(request, "once")
      } catch {
        state.guard = null
        throw new Error("P0_PERMISSION_REPLY_FAILED")
      }
    },

    "shell.env": async (input, output) => {
      const state =
        typeof input?.sessionID === "string" && typeof input?.callID === "string"
          ? calls.get(key(input.sessionID, input.callID))
          : undefined
      if (!state?.guard) return

      if (!(await exactRuntimeReady())) throw new Error("P0_RUNTIME_PROFILE_DRIFT")
      if (Object.keys(output?.env || {}).length !== 0) throw new Error("P0_ENVIRONMENT_TRANSFORM_UNEXPECTED")

      let payload
      try {
        payload = runAdapter(
          bundle,
          "revalidate",
          ["--command", state.command, "--cwd", state.cwd, "--workspace-root", directory],
          state.guard,
        )
      } catch {
        throw new Error("P0_AUTHORIZATION_REVALIDATION_FAILED")
      }
      if (payload?.ok !== true) throw new Error("P0_AUTHORIZATION_BINDING_INVALID")
    },

    "tool.execute.after": async (input) => {
      if (input.tool !== "bash") return
      calls.delete(key(input.sessionID, input.callID))
    },
  }
}

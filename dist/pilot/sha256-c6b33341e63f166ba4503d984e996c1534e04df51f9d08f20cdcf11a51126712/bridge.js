import crypto from "node:crypto"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { spawnSync } from "node:child_process"

const DOMAIN = "opencode_permissions.pilot_artifact.v1\n"
const METRICS_SCHEMA = "opencode-permissions-p0-metrics/v1"
const METRICS_SCOPE = "ask_path"
const METRICS_REGISTRY = Symbol.for("opencode_permissions.p0.metrics.v1")
const METRIC_COUNTERS = [
  "native_ask",
  "classifier_allow",
  "classifier_deny",
  "residual_ask",
  "classifier_error/fail_closed",
  "binding_reject",
]
const MAX_BUCKETS = 64
const SAFE_BUCKET = /^[A-Za-z0-9_.:/-]{1,96}$/

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

function verifyMetricsContract(manifest, profile) {
  const metrics = profile?.metrics
  if (metrics?.schema !== METRICS_SCHEMA) throw new Error("P0_METRICS_SCHEMA_MISMATCH")
  if (metrics?.scope !== METRICS_SCOPE) throw new Error("P0_METRICS_SCOPE_MISMATCH")
  if (metrics?.required_for_classifier_allow !== true) throw new Error("P0_METRICS_ALLOW_NOT_REQUIRED")
  if (metrics?.raw_inputs !== false) throw new Error("P0_METRICS_RAW_INPUTS_FORBIDDEN")
  if (metrics?.storage !== "per_process_aggregate_snapshot") throw new Error("P0_METRICS_STORAGE_MISMATCH")
  if (metrics?.state_resolution !== "os_homedir_local_state") throw new Error("P0_METRICS_STATE_RESOLUTION_MISMATCH")
  if (metrics?.max_reason_buckets !== MAX_BUCKETS) throw new Error("P0_METRICS_BUCKET_LIMIT_MISMATCH")
  if (!Array.isArray(metrics?.counters) || stable(metrics.counters) !== stable(METRIC_COUNTERS)) {
    throw new Error("P0_METRICS_COUNTERS_MISMATCH")
  }
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
  if (path.basename(root) !== manifest.artifact_path_segment) throw new Error("P0_BUNDLE_DIRECTORY_MISMATCH")

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
  if (profile?.classifier_profile_id !== manifest?.classifier_profile?.id) throw new Error("P0_PROFILE_ID_MISMATCH")
  if (profile?.target?.opencode_version !== manifest?.target?.exact_version) throw new Error("P0_PROFILE_VERSION_MISMATCH")
  if (profile?.target?.compatibility_profile_id !== manifest?.target?.compatibility_profile_id) {
    throw new Error("P0_PROFILE_COMPATIBILITY_MISMATCH")
  }
  if (profile?.target?.native_policy_artifact_id !== manifest?.native_policy_artifact_id) {
    throw new Error("P0_PROFILE_NATIVE_ARTIFACT_MISMATCH")
  }
  verifyMetricsContract(manifest, profile)
  return { manifest, profile }
}

function runAdapter(bundle, action, args, guard = null) {
  const python = bundle.profile?.python_runtime?.path
  if (typeof python !== "string" || !path.isAbsolute(python)) throw new Error("P0_PYTHON_RUNTIME_INVALID")
  const command = [adapterPath, action, ...args, "--profile", profilePath]
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

function runtimeVersion() {
  const child = spawnSync(process.execPath, ["--version"], {
    encoding: "utf8",
    env: {},
    cwd: root,
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 10_000,
    maxBuffer: 1024 * 1024,
  })
  if (child.status !== 0 || child.error) return null
  const version = child.stdout.trim()
  return version || null
}

function metricRegistry() {
  if (!(globalThis[METRICS_REGISTRY] instanceof Map)) {
    Object.defineProperty(globalThis, METRICS_REGISTRY, {
      value: new Map(),
      configurable: false,
      enumerable: false,
      writable: false,
    })
  }
  return globalThis[METRICS_REGISTRY]
}

function emptyMetrics(bundle) {
  return {
    schema: METRICS_SCHEMA,
    scope: METRICS_SCOPE,
    opencode_version: bundle.manifest.target.exact_version,
    compatibility_profile: bundle.manifest.target.compatibility_profile_id,
    native_policy_artifact_id: bundle.manifest.native_policy_artifact_id,
    pilot_artifact_id: bundle.manifest.artifact_id,
    classifier_profile: bundle.profile.classifier_profile_id,
    counters: Object.fromEntries(METRIC_COUNTERS.map((name) => [name, 0])),
    reasons: { __other__: 0 },
    families: { __other__: 0 },
    updated_at: null,
  }
}

function metricsState(bundle) {
  const registry = metricRegistry()
  const artifact = bundle.manifest.artifact_id
  if (!registry.has(artifact)) registry.set(artifact, emptyMetrics(bundle))
  return registry.get(artifact)
}

function safeBucket(value) {
  return typeof value === "string" && SAFE_BUCKET.test(value) ? value : "__other__"
}

function incrementBucket(bucket, value) {
  let key = safeBucket(value)
  if (!(key in bucket) && Object.keys(bucket).length >= MAX_BUCKETS) key = "__other__"
  bucket[key] = (bucket[key] || 0) + 1
}

function metricsDirectory(bundle) {
  const home = os.homedir()
  if (typeof home !== "string" || !path.isAbsolute(home)) throw new Error("P0_METRICS_HOME_INVALID")
  const homeReal = fs.realpathSync(home)
  const directory = path.join(
    homeReal,
    ".local",
    "state",
    "opencode_permissions",
    "p0-metrics",
    bundle.manifest.artifact_path_segment,
  )
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 })
  const stat = fs.lstatSync(directory)
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error("P0_METRICS_DIRECTORY_INVALID")
  const directoryReal = fs.realpathSync(directory)
  if (directoryReal !== homeReal && !directoryReal.startsWith(homeReal + path.sep)) {
    throw new Error("P0_METRICS_DIRECTORY_ESCAPE")
  }
  fs.chmodSync(directoryReal, 0o700)
  return directoryReal
}

function persistMetrics(bundle, snapshot) {
  const directory = metricsDirectory(bundle)
  const destination = path.join(directory, `process-${process.pid}.json`)
  const temporary = path.join(
    directory,
    `.process-${process.pid}.${crypto.randomBytes(8).toString("hex")}.tmp`,
  )
  const data = `${JSON.stringify(snapshot, null, 2)}\n`
  let descriptor = null
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600)
    fs.writeFileSync(descriptor, data, { encoding: "utf8" })
    fs.fsyncSync(descriptor)
    fs.closeSync(descriptor)
    descriptor = null
    fs.renameSync(temporary, destination)
    fs.chmodSync(destination, 0o600)
  } finally {
    if (descriptor !== null) fs.closeSync(descriptor)
    try {
      fs.unlinkSync(temporary)
    } catch (error) {
      if (error?.code !== "ENOENT") throw error
    }
  }
}

function recordMetric(bundle, counter, { reason = null, family = null } = {}) {
  if (!METRIC_COUNTERS.includes(counter)) throw new Error("P0_METRICS_COUNTER_INVALID")
  const current = metricsState(bundle)
  const next = JSON.parse(JSON.stringify(current))
  next.counters[counter] += 1
  if (reason !== null) incrementBucket(next.reasons, reason)
  if (family !== null) incrementBucket(next.families, family)
  next.updated_at = new Date().toISOString()
  persistMetrics(bundle, next)
  metricRegistry().set(bundle.manifest.artifact_id, next)
}

function bestEffortMetric(bundle, counter, options = {}) {
  try {
    recordMetric(bundle, counter, options)
    return true
  } catch {
    return false
  }
}

function firstReason(payload, fallback) {
  const codes = payload?.result?.reason_codes
  return Array.isArray(codes) && typeof codes[0] === "string" ? codes[0] : fallback
}

export const OpenCodePermissionsP0 = async ({ client, directory }) => {
  const bundle = verifyBundle()
  const calls = new Map()
  const maxCalls = 1024
  let configuredShell = null
  let configSeen = false
  let versionChecked = false
  let versionValue = null

  async function exactRuntimeReady() {
    if (process.platform !== "linux" || !configSeen) return false
    if (configuredShell !== bundle.profile.shell.path) return false
    if (!versionChecked) {
      versionValue = runtimeVersion()
      versionChecked = true
    }
    return versionValue === bundle.manifest.target.exact_version
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

      // Without a persisted denominator, an automatic classifier ALLOW would be
      // unmeasurable. Leave the native ASK untouched when the metrics sink is unavailable.
      try {
        recordMetric(bundle, "native_ask")
      } catch {
        return
      }

      const callID = request?.tool?.callID
      const state = typeof callID === "string" ? calls.get(key(request.sessionID, callID)) : undefined

      if (!state || request?.metadata?.command !== state.command) {
        if (state) calls.delete(key(request.sessionID, callID))
        bestEffortMetric(bundle, "binding_reject", { reason: "binding.permission_event_mismatch" })
        await reply(request, "reject")
        return
      }

      if (!(await exactRuntimeReady())) {
        bestEffortMetric(bundle, "residual_ask", { reason: "runtime.not_ready" })
        return
      }

      let payload
      try {
        payload = runAdapter(
          bundle,
          "prepare",
          ["--command", state.command, "--cwd", state.cwd, "--workspace-root", directory],
        )
      } catch {
        bestEffortMetric(bundle, "classifier_error/fail_closed", { reason: "adapter.prepare_failed" })
        bestEffortMetric(bundle, "residual_ask", { reason: "adapter.prepare_failed" })
        return
      }

      const decision = payload?.result?.decision
      if (decision === "DENY") {
        calls.delete(key(request.sessionID, callID))
        bestEffortMetric(bundle, "classifier_deny", { reason: firstReason(payload, "classifier.deny") })
        await reply(request, "reject")
        return
      }
      if (decision !== "ALLOW" || !payload?.guard) {
        bestEffortMetric(bundle, "residual_ask", { reason: firstReason(payload, "classifier.ask") })
        return
      }

      state.guard = payload.guard
      try {
        await reply(request, "once")
      } catch {
        state.guard = null
        bestEffortMetric(bundle, "classifier_error/fail_closed", { reason: "permission.reply_failed" })
        bestEffortMetric(bundle, "residual_ask", { reason: "permission.reply_failed" })
        throw new Error("P0_PERMISSION_REPLY_FAILED")
      }
    },

    "shell.env": async (input, output) => {
      const state =
        typeof input?.sessionID === "string" && typeof input?.callID === "string"
          ? calls.get(key(input.sessionID, input.callID))
          : undefined
      if (!state?.guard) return

      if (!(await exactRuntimeReady())) {
        bestEffortMetric(bundle, "binding_reject", { reason: "binding.runtime_profile_drift" })
        throw new Error("P0_RUNTIME_PROFILE_DRIFT")
      }
      if (input.cwd !== state.cwd) {
        bestEffortMetric(bundle, "binding_reject", { reason: "binding.cwd_drift" })
        throw new Error("P0_CWD_BINDING_DRIFT")
      }
      if (Object.keys(output?.env || {}).length !== 0) {
        bestEffortMetric(bundle, "binding_reject", { reason: "binding.environment_transform" })
        throw new Error("P0_ENVIRONMENT_TRANSFORM_UNEXPECTED")
      }

      let payload
      try {
        payload = runAdapter(
          bundle,
          "revalidate",
          ["--command", state.command, "--cwd", input.cwd, "--workspace-root", directory],
          state.guard,
        )
      } catch {
        bestEffortMetric(bundle, "binding_reject", { reason: "binding.revalidation_failed" })
        throw new Error("P0_AUTHORIZATION_REVALIDATION_FAILED")
      }
      if (payload?.ok !== true) {
        bestEffortMetric(bundle, "binding_reject", { reason: payload?.reason || "binding.invalid" })
        throw new Error("P0_AUTHORIZATION_BINDING_INVALID")
      }

      // Required write comes after authorization binding revalidation and before execution.
      // If it cannot be persisted, no classifier-controlled execution is allowed.
      try {
        recordMetric(bundle, "classifier_allow", { family: "grep.single_nonsecret_workspace_file" })
      } catch {
        throw new Error("P0_METRICS_WRITE_FAILED")
      }
    },

    "tool.execute.after": async (input) => {
      if (input.tool !== "bash") return
      calls.delete(key(input.sessionID, input.callID))
    },
  }
}

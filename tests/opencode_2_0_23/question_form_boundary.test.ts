// Runs against immutable upstream 2.0.23. No model, shell, SSH or external owner.
import { expect } from "bun:test"
import { Deferred, Effect, Fiber, Layer } from "effect"
import { Agent } from "@opencode/core/agent"
import { Database } from "@opencode/core/database/database"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { LayerNode } from "@opencode/util/effect/layer-node"
import { makeLocationNode } from "@opencode/util/effect/app-node"
import { Bus } from "@opencode/core/bus"
import { Form } from "@opencode/core/form"
import { Image } from "@opencode/core/image"
import { Location } from "@opencode/core/location"
import { Permission } from "@opencode/core/permission"
import { PermissionSaved } from "@opencode/core/permission/saved"
import { Project } from "@opencode/core/project"
import { ProjectTable } from "@opencode/core/project/sql"
import { AbsolutePath } from "@opencode/core/schema"
import { Session } from "@opencode/core/session"
import { SessionTable } from "@opencode/core/session/sql"
import { SessionStore } from "@opencode/core/session/store"
import { Tool } from "@opencode/core/tool"
import { QuestionTool } from "@opencode/core/tool/plugin/question"
import { location } from "./fixture/location"
import { testEffect } from "./lib/effect"
import { imagePassthrough } from "./lib/image"
import { executeTool, registerToolPlugin, toolIdentity } from "./lib/tool"

const current = Layer.succeed(Location.Service,
  Location.Service.of(location({ directory: AbsolutePath.make("/project") })))
const questionNode = makeLocationNode({
  name: "test/batch-question-plugin",
  layer: Layer.effectDiscard(registerToolPlugin(QuestionTool.Plugin)),
  deps: [Tool.node, Permission.node, Form.node],
})
const it = testEffect(AppNodeBuilder.build(LayerNode.group([
  Database.node, Bus.node, SessionStore.node, PermissionSaved.node, Agent.node,
  Permission.node, Form.node, Tool.node, questionNode,
]), [Location.node.replace(current), Image.node.replace(imagePassthrough)]))
const sessionID = Session.ID.make("ses_batch_question")
const otherID = Session.ID.make("ses_other_question")
const questions = [1, 2, 3].map(i => ({
  question: `Synthetic choice ${i}`, header: `Choice ${i}`,
  options: [{ label: `A${i}`, description: "First" }, { label: `B${i}`, description: "Second" }],
}))

function setup(effect: "allow" | "ask" | "deny" = "allow") {
  return Effect.gen(function* () {
    const db = yield* Database.Service
    yield* db.db.insert(ProjectTable).values({
      id: Project.ID.global, worktree: AbsolutePath.make("/project"), sandboxes: [],
    }).onConflictDoNothing().run().pipe(Effect.orDie)
    for (const id of [sessionID, otherID]) {
      yield* db.db.insert(SessionTable).values({ id, project_id: Project.ID.global,
        slug: String(id), directory: "/project", title: "synthetic Q", version: "2.0.23", agent: "build",
      }).onConflictDoNothing().run().pipe(Effect.orDie)
    }
    const agents = yield* Agent.Service
    yield* agents.transform(editor => editor.update(Agent.ID.make("build"), agent => {
      agent.permissions = [
        { action: "question", resource: "*", effect },
        { action: "sudo_job.start", resource: "*", effect: "ask" },
        { action: "sudo_job.stop", resource: "*", effect: "deny" },
      ]
    }))
  })
}

function launch(input = questions, owner = sessionID) {
  return Effect.gen(function* () {
    const forms = yield* Form.Service
    const bus = yield* Bus.Service
    const registry = yield* Tool.Service
    const observed = yield* Deferred.make<Form.Info>()
    const created: Form.Info[] = []
    const call = `call_${String(owner)}_${input.length}`
    const unsubscribe = yield* bus.listen(event => {
      if (event.type !== Form.Event.Created.type) return Effect.void
      const form = (event.data as { form: Form.Info }).form
      if (form.sessionID !== owner) return Effect.void
      created.push(form)
      return Deferred.succeed(observed, form).pipe(Effect.asVoid)
    })
    yield* Effect.addFinalizer(() => unsubscribe)
    const fiber = yield* executeTool(registry, {
      sessionID: owner, ...toolIdentity,
      call: { type: "tool-call", id: call, name: "question", input: { questions: input } },
    }).pipe(Effect.forkScoped)
    const form = yield* Deferred.await(observed)
    expect(form.metadata).toEqual({ kind: "question", tool: { messageID: toolIdentity.messageID, id: call } })
    expect(yield* forms.state(form.id)).toEqual({ status: "pending" })
    return { forms, fiber, form, created }
  })
}

it.effect("one native question produces one real form with three ordered fields", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* launch()
  expect(call.created.length).toBe(1)
  expect(call.form.fields.map(f => f.key)).toEqual(["q0", "q1", "q2"])
  yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1", q1: "B2", q2: "A3" } })
  const result = yield* Fiber.join(call.fiber)
  expect(result.status).toBe("completed")
  expect(result.output).toEqual({ answers: [["A1"], ["B2"], ["A3"]] })
  expect(result.metadata).toEqual({ answers: [["A1"], ["B2"], ["A3"]] })
  expect(yield* call.forms.list({ sessionID })).toEqual([])
  expect((yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1" } }).pipe(Effect.exit))._tag).toBe("Failure")
}))

it.effect("three sequential questions produce three real forms", () => Effect.gen(function* () {
  yield* setup()
  const ids: string[] = []
  for (const q of questions) {
    const call = yield* launch([q])
    ids.push(String(call.form.id))
    expect(call.created.length).toBe(1)
    yield* call.forms.reply({ id: call.form.id, answer: { q0: q.options[0].label } })
    expect((yield* Fiber.join(call.fiber)).output).toEqual({ answers: [[q.options[0].label]] })
  }
  expect(new Set(ids).size).toBe(3)
}))

it.effect("native question DENY creates no form", () => Effect.gen(function* () {
  yield* setup("deny")
  const registry = yield* Tool.Service
  const forms = yield* Form.Service
  const result = yield* executeTool(registry, { sessionID, ...toolIdentity,
    call: { type: "tool-call", id: "denied_question", name: "question", input: { questions } },
  })
  expect(result.status).toBe("error")
  expect(result.error?.type).toBe("permission.rejected")
  expect(yield* forms.list()).toEqual([])
}))

it.effect("question ASK stays separate from the eventual answer form", () => Effect.gen(function* () {
  yield* setup("ask")
  const permission = yield* Permission.Service
  const bus = yield* Bus.Service
  const forms = yield* Form.Service
  const registry = yield* Tool.Service
  const observed = yield* Deferred.make<Permission.Request>()
  const unsubscribe = yield* bus.listen(event => event.type === Permission.Event.Asked.type
    ? Deferred.succeed(observed, event.data as Permission.Request).pipe(Effect.asVoid) : Effect.void)
  yield* Effect.addFinalizer(() => unsubscribe)
  const fiber = yield* executeTool(registry, { sessionID, ...toolIdentity,
    call: { type: "tool-call", id: "asked_question", name: "question", input: { questions } },
  }).pipe(Effect.forkScoped)
  const request = yield* Deferred.await(observed)
  expect(request.action).toBe("question")
  expect(yield* forms.list()).toEqual([])
  yield* permission.reply({ requestID: request.id, reply: "reject" })
  // V2 deliberately tunnels a user's dismissal as a typed failing fiber,
  // rather than giving the model an ordinary error tool result.
  expect((yield* Fiber.await(fiber))._tag).toBe("Failure")
  expect(yield* permission.list()).toEqual([])
  expect(yield* forms.list()).toEqual([])
}))

it.effect("invalid form field does not partially settle the question", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* launch()
  expect((yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1", q9: "extra" } }).pipe(Effect.exit))._tag).toBe("Failure")
  expect(yield* call.forms.state(call.form.id)).toEqual({ status: "pending" })
  yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1", q1: "B2", q2: "A3" } })
  expect((yield* Fiber.join(call.fiber)).status).toBe("completed")
}))

it.effect("partial native answers remain explicit empty answers rather than approval", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* launch()
  yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1" } })
  expect((yield* Fiber.join(call.fiber)).output).toEqual({ answers: [["A1"], [], []] })
}))

it.effect("form cancellation and interruption block late replies", () => Effect.gen(function* () {
  yield* setup()
  for (const mode of ["cancel", "interrupt"] as const) {
    const call = yield* launch()
    if (mode === "cancel") yield* call.forms.cancel(call.form.id)
    else yield* Fiber.interrupt(call.fiber)
    expect((yield* Fiber.await(call.fiber))._tag).toBe("Failure")
    expect(yield* call.forms.state(call.form.id)).toEqual({ status: "cancelled" })
    expect(yield* call.forms.list({ sessionID })).toEqual([])
    expect((yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1" } }).pipe(Effect.exit))._tag).toBe("Failure")
  }
}))

it.effect("form close cancels the waiting native question", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* launch()
  yield* call.forms.close
  expect((yield* Fiber.await(call.fiber))._tag).toBe("Failure")
  expect(yield* call.forms.list()).toEqual([])
}))

it.effect("session-filtered observation does not confuse independent forms", () => Effect.gen(function* () {
  yield* setup()
  const first = yield* launch(questions, sessionID)
  const second = yield* launch(questions, otherID)
  expect((yield* first.forms.list({ sessionID })).map(f => f.id)).toEqual([first.form.id])
  expect((yield* first.forms.list({ sessionID: otherID })).map(f => f.id)).toEqual([second.form.id])
  yield* first.forms.reply({ id: first.form.id, answer: { q0: "A1", q1: "B2", q2: "A3" } })
  yield* Fiber.join(first.fiber)
  expect(yield* first.forms.state(second.form.id)).toEqual({ status: "pending" })
  yield* first.forms.cancel(second.form.id)
  yield* Fiber.await(second.fiber)
}))

it.effect("question answers do not approve another native ASK or bypass DENY", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* launch()
  const permission = yield* Permission.Service
  const bus = yield* Bus.Service
  const asked = yield* Deferred.make<Permission.Request>()
  const unsubscribe = yield* bus.listen(event => event.type === Permission.Event.Asked.type
    ? Deferred.succeed(asked, event.data as Permission.Request).pipe(Effect.asVoid) : Effect.void)
  yield* Effect.addFinalizer(() => unsubscribe)
  const executed: string[] = []
  const action = yield* permission.assert({ sessionID, agent: toolIdentity.agent,
    action: "sudo_job.start", resources: ["synthetic"], save: [],
  }).pipe(Effect.andThen(Effect.sync(() => executed.push("synthetic start"))), Effect.forkScoped)
  const request = yield* Deferred.await(asked)
  yield* call.forms.reply({ id: call.form.id, answer: { q0: "A1", q1: "B2", q2: "A3" } })
  yield* Fiber.join(call.fiber)
  expect(executed).toEqual([])
  expect(yield* permission.get(request.id)).toBeDefined()
  const denied = yield* permission.assert({ sessionID, agent: toolIdentity.agent,
    action: "sudo_job.stop", resources: ["synthetic"],
  }).pipe(Effect.exit)
  expect(denied._tag).toBe("Failure")
  expect(yield* (yield* PermissionSaved.Service).list({ projectID: Project.ID.global })).toEqual([])
  yield* permission.reply({ requestID: request.id, reply: "reject" })
  yield* Fiber.await(action)
  expect(executed).toEqual([])
}))

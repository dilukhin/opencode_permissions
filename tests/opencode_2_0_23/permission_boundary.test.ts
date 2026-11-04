// Исполняется в packages/core/test точного upstream, без SSH и root-операций.
import { expect } from "bun:test"
import { Deferred, Effect, Fiber, Layer } from "effect"
import { Agent } from "@opencode/core/agent"
import { Database } from "@opencode/core/database/database"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { LayerNode } from "@opencode/util/effect/layer-node"
import { Bus } from "@opencode/core/bus"
import { Location } from "@opencode/core/location"
import { Permission } from "@opencode/core/permission"
import { PermissionSaved } from "@opencode/core/permission/saved"
import { Project } from "@opencode/core/project"
import { ProjectTable } from "@opencode/core/project/sql"
import { AbsolutePath } from "@opencode/core/schema"
import { Session } from "@opencode/core/session"
import { SessionTable } from "@opencode/core/session/sql"
import { SessionStore } from "@opencode/core/session/store"
import { location } from "./fixture/location"
import { testEffect } from "./lib/effect"

const current = Layer.succeed(
  Location.Service,
  Location.Service.of(location({ directory: AbsolutePath.make("/project") })),
)
const it = testEffect(
  AppNodeBuilder.build(
    LayerNode.group([Database.node, Bus.node, SessionStore.node, PermissionSaved.node, Agent.node, Permission.node]),
    [Location.node.replace(current)],
  ),
)
const sessionID = Session.ID.make("ses_sudo_boundary")
const operation = Object.freeze({ action: "sudo_job.start", resource: "sha256:synthetic-operation" })

function setup(effect: "ask" | "deny" = "ask") {
  return Effect.gen(function* () {
    const database = yield* Database.Service
    yield* database.db.insert(ProjectTable).values({
      id: Project.ID.global, worktree: AbsolutePath.make("/project"), sandboxes: [],
    }).onConflictDoNothing().run().pipe(Effect.orDie)
    yield* database.db.insert(SessionTable).values({
      id: sessionID, project_id: Project.ID.global, slug: "boundary", directory: "/project",
      title: "synthetic", version: "2.0.23", agent: "test",
    }).onConflictDoNothing().run().pipe(Effect.orDie)
    const agents = yield* Agent.Service
    yield* agents.transform((editor) => editor.update(Agent.ID.make("test"), (agent) => {
      agent.permissions = [{ action: "sudo_job.*", resource: "*", effect }]
    }))
  })
}

function pending(action: string = operation.action) {
  return Effect.gen(function* () {
    const permission = yield* Permission.Service
    const bus = yield* Bus.Service
    const asked = yield* Deferred.make<Permission.Request>()
    const id = Permission.ID.create()
    const executed: string[] = []
    const unsubscribe = yield* bus.listen((event) => {
      if (event.type !== Permission.Event.Asked.type) return Effect.void
      const request = event.data as Permission.Request
      return request.id === id ? Deferred.succeed(asked, request).pipe(Effect.asVoid) : Effect.void
    })
    yield* Effect.addFinalizer(() => unsubscribe)
    const fiber = yield* permission.assert({ id, sessionID, action, resources: [operation.resource], save: [] }).pipe(
      Effect.andThen(Effect.sync(() => executed.push(action))),
      Effect.forkScoped,
    )
    const request = yield* Deferred.await(asked)
    expect(executed).toEqual([])
    return { permission, request, fiber, executed }
  })
}

it.effect("once возобновляет ту же ожидающую операцию, повтор отвергается", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* pending()
  yield* call.permission.reply({ requestID: call.request.id, reply: "once" })
  yield* Fiber.join(call.fiber)
  expect(call.executed).toEqual([operation.action])
  expect((yield* call.permission.reply({ requestID: call.request.id, reply: "once" }).pipe(Effect.exit))._tag).toBe("Failure")
  const saved = yield* PermissionSaved.Service
  expect(yield* saved.list({ projectID: Project.ID.global })).toEqual([])
  const next = yield* pending()
  expect(next.executed).toEqual([])
  yield* next.permission.reply({ requestID: next.request.id, reply: "reject" })
  yield* Fiber.await(next.fiber)
}))

it.effect("reject сохраняет запрет выполнения", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* pending()
  yield* call.permission.reply({ requestID: call.request.id, reply: "reject" })
  expect((yield* Fiber.await(call.fiber))._tag).toBe("Failure")
  expect(call.executed).toEqual([])
  expect(yield* call.permission.list()).toEqual([])
}))

it.effect("configured deny блокирует до запроса согласия", () => Effect.gen(function* () {
  yield* setup("deny")
  const permission = yield* Permission.Service
  const executed: string[] = []
  const result = yield* permission.assert({ sessionID, action: operation.action, resources: [operation.resource] }).pipe(
    Effect.andThen(Effect.sync(() => executed.push(operation.action))), Effect.exit,
  )
  expect(result._tag).toBe("Failure")
  expect(executed).toEqual([])
  expect(yield* permission.list()).toEqual([])
}))

it.effect("отмена ожидающего вызова удаляет запрос и блокирует поздний once", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* pending()
  yield* Fiber.interrupt(call.fiber)
  expect(call.executed).toEqual([])
  expect(yield* call.permission.list()).toEqual([])
  expect((yield* call.permission.reply({ requestID: call.request.id, reply: "once" }).pipe(Effect.exit))._tag).toBe("Failure")
}))

it.effect("закрытие host отклоняет ожидающее разрешение", () => Effect.gen(function* () {
  yield* setup()
  const call = yield* pending()
  yield* call.permission.close
  expect((yield* Fiber.await(call.fiber))._tag).toBe("Failure")
  expect(call.executed).toEqual([])
  expect(yield* call.permission.list()).toEqual([])
}))

it.effect("разрешение start не разрешает отдельный stop", () => Effect.gen(function* () {
  yield* setup()
  const start = yield* pending()
  const stop = yield* pending("sudo_job.stop")
  yield* start.permission.reply({ requestID: start.request.id, reply: "once" })
  yield* Fiber.join(start.fiber)
  expect(start.executed).toEqual([operation.action])
  expect(stop.executed).toEqual([])
  expect(yield* stop.permission.get(stop.request.id)).toBeDefined()
  yield* stop.permission.reply({ requestID: stop.request.id, reply: "reject" })
  yield* Fiber.await(stop.fiber)
}))

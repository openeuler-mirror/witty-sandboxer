/**
 * Smoke test for the OpenSandbox Agent Infra plugin.
 *
 * Run with:  bun run opencode-plugin/smoke_test.ts
 *
 * The test is self-contained: it builds a temporary workspace, copies the
 * plugin + runner into it, symlinks the @opencode-ai/plugin node_modules,
 * then dynamically imports the plugin and exercises it.
 *
 * Coverage:
 *   1. Plugin structure  — 7 tools with correct names / args / execute fns.
 *   2. Python runner CLI — argparse, subcommands, missing-arg validation.
 *   3. Plugin → runner wiring — JSON parse path (stub runner) + real runner.
 *   4. Live E2E — only if an OpenSandbox server is reachable; otherwise the
 *      real-runner error path is asserted instead.
 */

import * as fs from "node:fs"
import * as path from "node:path"
import assert from "node:assert"
import { spawn } from "node:child_process"

const BUN = "/home/greatwall/.bun/bin/bun"
const HERE = path.dirname(new URL(import.meta.url).pathname)
const PLUGIN_SRC = path.join(HERE, "agent-sandbox-infra.ts")
const RUNNER_SRC = path.join(HERE, "sandbox_runner.py")
const NM_SRC = "/home/greatwall/.opencode/node_modules"
const TMP = "/tmp/sandbox-smoke"

const EXPECTED_TOOLS = [
  "sandbox_create",
  "sandbox_exec",
  "sandbox_upload",
  "sandbox_upload_text",
  "sandbox_download",
  "sandbox_download_dir",
  "sandbox_destroy",
]

/** Plugin tools return { output, metadata }; assertions read the parsed body. */
function body(result: any): any {
  return result?.metadata ?? result
}

// ─── tiny test harness ────────────────────────────────────────
type R = { name: string; ok: boolean; err?: string }
const results: R[] = []
async function test(name: string, fn: () => Promise<void> | void) {
  try {
    await fn()
    results.push({ name, ok: true })
    console.log(`  ✓ ${name}`)
  } catch (e: any) {
    results.push({ name, ok: false, err: e?.stack || String(e) })
    console.log(`  ✗ ${name}\n${e?.stack || e}`)
  }
}

// ─── helpers ──────────────────────────────────────────────────
function run(cmd: string, args: string[], opts: { cwd?: string; env?: Record<string,string> } = {}): Promise<{code:number;stdout:string;stderr:string}> {
  return new Promise((resolve) => {
    let p: any
    try {
      p = spawn(cmd, args, { cwd: opts.cwd, env: { ...process.env, ...(opts.env||{}) } })
    } catch (e: any) {
      resolve({ code: -127, stdout: "", stderr: String(e) })
      return
    }
    let stdout = "", stderr = ""
    p.stdout.on("data", (d: any) => (stdout += d))
    p.stderr.on("data", (d: any) => (stderr += d))
    p.on("error", () => resolve({ code: -127, stdout, stderr }))
    p.on("close", (code: number | null) => resolve({ code: code ?? -1, stdout, stderr }))
  })
}

async function sha256(p: string): Promise<string> {
  const buf = await Bun.file(p).arrayBuffer()
  const h = await crypto.subtle.digest("SHA-256", buf)
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("")
}

async function probeServer(): Promise<boolean> {
  // SDK default domain is localhost:8080; /health returns 200 when the server is up.
  // GET / is 404 even on a healthy server, so it cannot be used as a liveness check.
  const r = await run(PYTHON, ["-c", "import urllib.request,sys\ntry:\n  urllib.request.urlopen('http://localhost:8080/health',timeout=2)\n  print('up')\nexcept Exception:\n  print('down')\n"])
  return r.stdout.trim() === "up"
}

/** Find a python3 that can `import opensandbox` and put it first on PATH.
 *  Also set PYTHONPATH to the repo root so the local `opensandbox` SDK package
 *  (shipped as source under agent-sandbox/opensandbox) is importable when the
 *  runner script is executed (script execution puts the script's dir, not the
 *  cwd, on sys.path[0]). */
let PYTHON = "python3"
const REPO_ROOT = path.resolve(HERE, "..")
async function resolvePython(): Promise<void> {
  process.env.PYTHONPATH = REPO_ROOT + ":" + (process.env.PYTHONPATH || "")
  const candidates = [
    "python3", "/usr/local/bin/python3.12", "/usr/bin/python3",
    "/data/usershare/gerrit/kylin-agent-sdk/agent-security/agent-sec-cli/.venv/bin/python3",
    "/data/usershare/gerrit/kylin-agent-sdk/agent-security/sandbox-policy/.venv/bin/python3",
    "/usr/bin/python3.11", "/usr/bin/python3.10", "/usr/bin/python3.12",
  ]
  for (const c of candidates) {
    const r = await run(c, ["-c", "import sys; from opensandbox import Sandbox; print('OK', sys.executable)"])
    if (r.code === 0 && /^OK/.test(r.stdout.trim())) {
      PYTHON = c
      const dir = path.dirname(c)
      process.env.PATH = dir + ":" + (process.env.PATH || "")
      return
    }
  }
  throw new Error("No python3 with opensandbox module found (tried PYTHONPATH=" + process.env.PYTHONPATH + ")")
}

// ─── workspace setup ─────────────────────────────────────────
function setupWorkspace(name: string, runnerContent?: string): string {
  const ws = path.join(TMP, name)
  fs.rmSync(ws, { recursive: true, force: true })
  fs.mkdirSync(path.join(ws, ".opencode", "plugins"), { recursive: true })
  fs.mkdirSync(path.join(ws, "node_modules"), { recursive: true })
  // symlink @opencode-ai so the copied plugin can resolve it
  try { fs.symlinkSync(NM_SRC + "/@opencode-ai", path.join(ws, "node_modules", "@opencode-ai")) } catch {}
  // copy plugin
  fs.copyFileSync(PLUGIN_SRC, path.join(ws, "agent-sandbox-infra.ts"))
  // runner: real or stub
  fs.writeFileSync(path.join(ws, ".opencode", "plugins", "sandbox_runner.py"),
    runnerContent ?? fs.readFileSync(RUNNER_SRC, "utf8"))
  return ws
}

// ─── main ────────────────────────────────────────────────────
async function main() {
  fs.rmSync(TMP, { recursive: true, force: true })
  fs.mkdirSync(TMP, { recursive: true })
  await resolvePython()
  console.log(`using python: ${PYTHON}`)

  console.log("\n=== 1. Plugin structure ===")
  const ws = setupWorkspace("ws")
  const pluginHash = await sha256(PLUGIN_SRC)
  const copyHash = await sha256(path.join(ws, "agent-sandbox-infra.ts"))
  await test("plugin copy is byte-identical to source", () => assert.strictEqual(copyHash, pluginHash))

  const mod: any = await import(path.join(ws, "agent-sandbox-infra.ts"))
  const plugin = await mod.SandboxInfraPlugin()
  await test("default export is the plugin function", () =>
    assert.strictEqual(mod.default, mod.SandboxInfraPlugin))
  await test("every export is a function (OpenCode legacy loader throws otherwise)", () => {
    const values = Object.values(mod)
    assert.ok(values.length > 0)
    for (const value of values) assert.strictEqual(typeof value, "function")
  })
  await test("tool args are JSON Schema, not a Zod instance", () => {
    const image = plugin.tool.sandbox_create.args.image
    assert.deepStrictEqual(image, {
      type: "string",
      description: image.description,
    })
    assert.ok(!("_zod" in image), "zod args fail to register when host zod differs")
  })
  await test("SandboxInfraPlugin returns { tool }", () => assert.ok(plugin?.tool, "no tool map"))
  await test("exactly 7 tools", () =>
    assert.deepStrictEqual(Object.keys(plugin.tool).sort(), EXPECTED_TOOLS.slice().sort()))
  for (const name of EXPECTED_TOOLS) {
    await test(`${name} has description+args+execute`, () => {
      const t = plugin.tool[name]
      assert.ok(typeof t?.description === "string" && t.description.length > 0, "description")
      assert.ok(t?.args && typeof t.args === "object", "args")
      assert.ok(typeof t?.execute === "function", "execute")
    })
  }
  await test("sandbox_create args: image/cpu/memory/timeout", () =>
    assert.deepStrictEqual(Object.keys(plugin.tool.sandbox_create.args).sort(),
      ["cpu","image","memory","timeout"]))
  await test("sandbox_exec args: sandbox_id/command/timeout/workdir", () =>
    assert.deepStrictEqual(Object.keys(plugin.tool.sandbox_exec.args).sort(),
      ["command","sandbox_id","timeout","workdir"]))
  await test("sandbox_destroy args: sandbox_id", () =>
    assert.deepStrictEqual(Object.keys(plugin.tool.sandbox_destroy.args).sort(), ["sandbox_id"]))

  console.log("\n=== 2. Python runner CLI ===")
  const runner = path.join(ws, ".opencode", "plugins", "sandbox_runner.py")
  await test("runner --help exits 0", async () => {
    const r = await run(PYTHON, [runner, "--help"])
    assert.strictEqual(r.code, 0, `exit=${r.code} stderr=${r.stderr}`)
    for (const sub of ["create","exec","upload","upload_text","download","download_dir","destroy"]) {
      assert.ok(r.stdout.includes(sub), `help missing ${sub}`)
    }
  })
  await test("runner invalid subcommand exits !=0", async () => {
    const r = await run(PYTHON, [runner, "nope"])
    assert.notStrictEqual(r.code, 0)
  })
  await test("runner exec missing required args exits !=0", async () => {
    const r = await run(PYTHON, [runner, "exec"])
    assert.notStrictEqual(r.code, 0)
    assert.ok(/required/i.test(r.stderr), `stderr=${r.stderr}`)
  })
  await test("runner has no csv_analyze subcommand", async () => {
    const r = await run(PYTHON, [runner, "--help"])
    assert.ok(!/csv_analyze/.test(r.stdout), "csv_analyze should be removed")
  })

  console.log("\n=== 3. Plugin → runner wiring ===")
  // 3a: stub runner → JSON parse path
  const stubWs = setupWorkspace("stubws", [
    "#!/usr/bin/env python3",
    "import json, sys",
    'print(json.dumps({"status":"ok","sandbox_id":"stub-123","echo":sys.argv[1:]}))',
    "",
  ].join("\n"))
  await test("stub runner: sandbox_create returns ToolResult with string output", async () => {
    const ctx = { directory: stubWs, worktree: stubWs }
    const out: any = await plugin.tool.sandbox_create.execute({ image: "python:3.12" }, ctx)
    // OpenCode calls output.split("\n"); a missing output string is the c.split crash.
    assert.strictEqual(typeof out?.output, "string")
    out.output.split("\n")
    const parsed = body(out)
    assert.strictEqual(parsed?.status, "ok")
    assert.strictEqual(parsed?.sandbox_id, "stub-123")
    assert.deepStrictEqual(JSON.parse(out.output), parsed)
  })
  await test("stub runner: sandbox_exec forwards args", async () => {
    const ctx = { directory: stubWs, worktree: stubWs }
    const out: any = await plugin.tool.sandbox_exec.execute(
      { sandbox_id: "sb-x", command: "echo hi" }, ctx)
    const parsed = body(out)
    assert.strictEqual(parsed?.status, "ok")
    assert.ok(Array.isArray(parsed?.echo) && parsed.echo.includes("exec"), JSON.stringify(out))
  })

  // 3b: real runner
  const serverUp = await probeServer()
  if (serverUp) {
    console.log("\n=== 4. Live E2E (server reachable) ===")
    let sid = ""
    try {
      const c: any = await plugin.tool.sandbox_create.execute({ image: "python:3.12" },
        { directory: ws, worktree: ws })
      sid = body(c)?.sandbox_id
      await test("create returns sandbox_id", () => assert.ok(sid, JSON.stringify(c)))
      const e: any = await plugin.tool.sandbox_exec.execute(
        { sandbox_id: sid, command: "echo hello-smoke" }, { directory: ws, worktree: ws })
      await test("exec echo", () => {
        const parsed = body(e)
        assert.strictEqual(parsed?.status, "ok", JSON.stringify(e))
        assert.ok(/hello-smoke/.test(parsed?.stdout || ""), JSON.stringify(e))
      })
      const ut: any = await plugin.tool.sandbox_upload_text.execute(
        { sandbox_id: sid, remote_path: "/home/user/note.txt", text: "smoke-content" },
        { directory: ws, worktree: ws })
      await test("upload_text", () => assert.strictEqual(body(ut)?.status, "ok", JSON.stringify(ut)))
      const cat: any = await plugin.tool.sandbox_exec.execute(
        { sandbox_id: sid, command: "cat /home/user/note.txt" }, { directory: ws, worktree: ws })
      await test("exec cat reads uploaded text", () =>
        assert.ok(/smoke-content/.test(body(cat)?.stdout || ""), JSON.stringify(cat)))
      const local = path.join(TMP, "local.txt"); fs.writeFileSync(local, "local-bytes")
      const up: any = await plugin.tool.sandbox_upload.execute(
        { sandbox_id: sid, local_path: local, remote_path: "/home/user/local.txt" },
        { directory: ws, worktree: ws })
      await test("upload local file", () => assert.strictEqual(body(up)?.status, "ok", JSON.stringify(up)))
      const dl = path.join(TMP, "downloaded.txt")
      const d: any = await plugin.tool.sandbox_download.execute(
        { sandbox_id: sid, remote_path: "/home/user/local.txt", local_path: dl },
        { directory: ws, worktree: ws })
      await test("download round-trips bytes", () => {
        assert.strictEqual(body(d)?.status, "ok", JSON.stringify(d))
        assert.strictEqual(fs.readFileSync(dl, "utf8"), "local-bytes")
      })
      const dlDir = path.join(TMP, "dldir"); fs.mkdirSync(dlDir, { recursive: true })
      const dd: any = await plugin.tool.sandbox_download_dir.execute(
        { sandbox_id: sid, remote_dir: "/home/user", local_dir: dlDir, pattern: "*.txt" },
        { directory: ws, worktree: ws })
      await test("download_dir pulls >=1 txt", () => {
        const parsed = body(dd)
        assert.strictEqual(parsed?.status, "ok", JSON.stringify(dd))
        assert.ok((parsed?.count ?? 0) >= 1, JSON.stringify(dd))
      })
    } finally {
      if (sid) {
        await test("destroy", async () => {
          const r: any = await plugin.tool.sandbox_destroy.execute(
            { sandbox_id: sid }, { directory: ws, worktree: ws })
          assert.strictEqual(body(r)?.status, "ok", JSON.stringify(r))
        })
      }
    }
  } else {
    console.log("\n=== 4. Real-runner error path (server NOT reachable) ===")
    await test("real runner: create throws 'sandbox_runner failed'", async () => {
      let err: any
      try {
        await plugin.tool.sandbox_create.execute({ image: "python:3.12" },
          { directory: ws, worktree: ws })
      } catch (e) { err = e }
      assert.ok(err instanceof Error, "should throw")
      assert.ok(/sandbox_runner failed/.test(err.message), err.message)
    })
    console.log("    (skipped live E2E — no OpenSandbox server at localhost:8080)")
  }

  // ─── summary ───────────────────────────────────────────────
  const passed = results.filter((r) => r.ok).length
  const failed = results.length - passed
  console.log(`\n─────────────────────────────────────────────`)
  console.log(`  ${passed}/${results.length} passed, ${failed} failed`)
  if (failed > 0) {
    console.log("  FAILED:")
    results.filter((r) => !r.ok).forEach((r) => console.log(`   - ${r.name}`))
  }
  process.exit(failed > 0 ? 1 : 0)
}

main().catch((e) => { console.error(e); process.exit(1) })

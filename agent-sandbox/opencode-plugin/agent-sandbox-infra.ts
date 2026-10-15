import path from "path"
import { existsSync } from "node:fs"

/**
 * OpenSandbox Agent Infra Plugin
 * ==============================
 *
 * A general-purpose agent infrastructure plugin that gives the AI agent
 * full control over OpenSandbox containers.  Instead of one monolithic
 * tool, this plugin exposes **seven composable primitives**:
 *
 *   sandbox_create      — Spin up a container, return its ID
 *   sandbox_exec        — Run a shell command inside a sandbox
 *   sandbox_upload      — Upload a local file into a sandbox
 *   sandbox_upload_text — Write text content to a remote path
 *   sandbox_download    — Download a file from a sandbox to local
 *   sandbox_download_dir— Download multiple files (glob) from a sandbox
 *   sandbox_destroy     — Destroy a sandbox
 *
 * The agent can compose these primitives into any workflow, e.g.:
 *   create → upload → exec (install deps) → exec (run script) → download → destroy
 *
 * Tool results use OpenCode's ToolResult shape: `output` is the JSON string
 * the model sees, `metadata` is the parsed runner object.
 */

/** Resolve the path to the Python runner script.
 *
 *  Lookup order:
 *    1. The directory this plugin file lives in (sibling to sandbox_runner.py).
 *       This handles both `make install` (project .opencode/plugins/) and
 *       `make install-global` (~/.config/opencode/plugins/), because in both
 *       cases agent-sandbox-infra.ts and sandbox_runner.py are copied together
 *       into the same directory.
 *    2. Fallback to <project>/.opencode/plugins/sandbox_runner.py for legacy
 *       installs where only the .ts was placed on the plugin path.
 */
function runnerPath(context: { directory: string; worktree?: string }): string {
  // import.meta.dir = directory of agent-sandbox-infra.ts (Bun).
  const here = import.meta.dir
  const sibling = path.join(here, "sandbox_runner.py")
  if (existsSync(sibling)) return sibling
  const root = context.worktree || context.directory
  return path.join(root, ".opencode", "plugins", "sandbox_runner.py")
}

/**
 * OpenCode's plugin registry does `truncate.output(result.output)`, and
 * truncation calls `text.split("\n")`. A bare object (no `output` string)
 * makes that `undefined.split` and surfaces as
 * "undefined is not an object (evaluating 'c.split')".
 * Always return the ToolResult shape: string `output` plus parsed `metadata`.
 */
function toToolResult(parsed: Record<string, unknown>) {
  const message = typeof parsed.message === "string" ? parsed.message : undefined
  const sandboxID = typeof parsed.sandbox_id === "string" ? parsed.sandbox_id : undefined
  return {
    title: message ?? sandboxID ?? "sandbox",
    output: JSON.stringify(parsed),
    metadata: parsed,
  }
}

/**
 * Tool args are plain JSON Schema, not Zod from `@opencode-ai/plugin`.
 *
 * OpenCode installs that package into the config directory at startup. On an
 * intranet host that install often fails, so a value import never resolves and
 * the plugin is skipped — the tools never reach the agent. Even when the
 * package is present, its Zod copy must be the same instance the host uses;
 * a mismatch throws inside tool registration and the tools are dropped.
 *
 * The host treats non-Zod args as JSON Schema (`legacyJsonSchema`).
 */
type ArgSchema = { type: "string" | "number"; description: string }

function str(description: string): ArgSchema {
  return { type: "string", description }
}

function num(description: string): ArgSchema {
  return { type: "number", description }
}

function tool<Args extends Record<string, ArgSchema>>(input: {
  description: string
  args: Args
  execute(
    args: { [K in keyof Args]?: string | number },
    context: { directory: string; worktree?: string },
  ): Promise<{ title: string; output: string; metadata: Record<string, unknown> }>
}) {
  return input
}

/** Execute the Python runner with the given subcommand + flags, return a ToolResult. */
async function runRunner(
  context: { directory: string; worktree?: string },
  args: string[]
): Promise<{ title: string; output: string; metadata: Record<string, unknown> }> {
  const script = runnerPath(context)
  const cmdArgs = ["python3", script, ...args]
  try {
    const raw = await Bun.$`${cmdArgs}`.text()
    // The runner prints exactly one JSON line per invocation.
    const lines = raw.trim().split("\n")
    const jsonLine = lines.find((l) => l.startsWith("{")) || lines[lines.length - 1]
    return toToolResult(JSON.parse(jsonLine))
  } catch (e: any) {
    const detail = e?.stderr || e?.stdout || e?.message || String(e)
    throw new Error(`sandbox_runner failed:\n${detail}`)
  }
}

export const SandboxInfraPlugin = async () => {
  return {
    tool: {
      // ──────────────────────────────────────────
      //  sandbox_create
      // ──────────────────────────────────────────
      sandbox_create: tool({
        description:
          "Create a new OpenSandbox container instance. Returns the sandbox ID which is needed for all subsequent operations (exec, upload, download, destroy). Always call sandbox_destroy when done to clean up.",
        args: {
          image: str("Container image (default: opensandbox/code-interpreter:v1.1.0). Optional."),
          cpu: str("CPU limit, e.g. '1' or '2'. Optional."),
          memory: str("Memory limit, e.g. '500Mi' or '2Gi'. Optional."),
          timeout: num("Sandbox lifetime in seconds (default: 900 = 15 min). Optional."),
        },
        async execute(args, context) {
          const flags = ["create"]
          if (args.image) flags.push("--image", args.image)
          if (args.cpu) flags.push("--cpu", args.cpu)
          if (args.memory) flags.push("--memory", args.memory)
          if (args.timeout) flags.push("--timeout", String(args.timeout))
          return runRunner(context, flags)
        },
      }),

      // ──────────────────────────────────────────
      //  sandbox_exec
      // ──────────────────────────────────────────
      sandbox_exec: tool({
        description:
          "Execute a shell command inside an existing sandbox. Returns stdout, stderr, and exit code. The sandbox must have been created via sandbox_create first.",
        args: {
          sandbox_id: str("ID of the sandbox (from sandbox_create)"),
          command: str("Shell command to execute"),
          timeout: num("Command timeout in seconds (default: 120). Optional."),
          workdir: str("Working directory inside the sandbox. Optional."),
        },
        async execute(args, context) {
          const flags = ["exec", "--sandbox-id", args.sandbox_id, "--command", args.command]
          if (args.timeout) flags.push("--timeout", String(args.timeout))
          if (args.workdir) flags.push("--workdir", args.workdir)
          return runRunner(context, flags)
        },
      }),

      // ──────────────────────────────────────────
      //  sandbox_upload
      // ──────────────────────────────────────────
      sandbox_upload: tool({
        description:
          "Upload a local file into a sandbox. Useful for uploading data files, scripts, or source code before executing them.",
        args: {
          sandbox_id: str("ID of the sandbox"),
          local_path: str("Path to the local file to upload"),
          remote_path: str("Destination path inside the sandbox, e.g. /home/user/script.py"),
        },
        async execute(args, context) {
          return runRunner(context, [
            "upload",
            "--sandbox-id", args.sandbox_id,
            "--local-path", args.local_path,
            "--remote-path", args.remote_path,
          ])
        },
      }),

      // ──────────────────────────────────────────
      //  sandbox_upload_text
      // ──────────────────────────────────────────
      sandbox_upload_text: tool({
        description:
          "Write text content directly to a file inside a sandbox, without needing a local file. Ideal for writing scripts or configs generated by the agent.",
        args: {
          sandbox_id: str("ID of the sandbox"),
          remote_path: str("Destination path inside the sandbox"),
          text: str("Text content to write"),
        },
        async execute(args, context) {
          return runRunner(context, [
            "upload_text",
            "--sandbox-id", args.sandbox_id,
            "--remote-path", args.remote_path,
            "--text", args.text,
          ])
        },
      }),

      // ──────────────────────────────────────────
      //  sandbox_download
      // ──────────────────────────────────────────
      sandbox_download: tool({
        description:
          "Download a single file from a sandbox to the local filesystem. Use this to retrieve generated outputs (charts, reports, data files).",
        args: {
          sandbox_id: str("ID of the sandbox"),
          remote_path: str("Path of the file inside the sandbox to download"),
          local_path: str("Local destination path for the downloaded file"),
        },
        async execute(args, context) {
          return runRunner(context, [
            "download",
            "--sandbox-id", args.sandbox_id,
            "--remote-path", args.remote_path,
            "--local-path", args.local_path,
          ])
        },
      }),

      // ──────────────────────────────────────────
      //  sandbox_download_dir
      // ──────────────────────────────────────────
      sandbox_download_dir: tool({
        description:
          "Download multiple files from a directory inside a sandbox. Supports glob pattern filtering (e.g. '*.png'). Returns the list of downloaded files.",
        args: {
          sandbox_id: str("ID of the sandbox"),
          remote_dir: str("Directory path inside the sandbox to download from"),
          local_dir: str("Local directory to save downloaded files"),
          pattern: str("Glob pattern to filter files, e.g. '*.png' or '*.csv'. Optional."),
        },
        async execute(args, context) {
          const flags = [
            "download_dir",
            "--sandbox-id", args.sandbox_id,
            "--remote-dir", args.remote_dir,
            "--local-dir", args.local_dir,
          ]
          if (args.pattern) flags.push("--pattern", args.pattern)
          return runRunner(context, flags)
        },
      }),

      // ──────────────────────────────────────────
      //  sandbox_destroy
      // ──────────────────────────────────────────
      sandbox_destroy: tool({
        description:
          "Destroy a sandbox instance and release all resources. Always call this when the sandbox is no longer needed.",
        args: {
          sandbox_id: str("ID of the sandbox to destroy"),
        },
        async execute(args, context) {
          return runRunner(context, [
            "destroy",
            "--sandbox-id", args.sandbox_id,
          ])
        },
      }),
    },
  }
}

export default SandboxInfraPlugin

/**
 * agent-behavior-sec — opencode 行为安全插件
 *
 * 把 sandbox-policy 的命令分类和 linux-sandbox 策略接到 opencode 钩子上。
 * 规则在 sandbox-policy 包里，本文件只做钩子接入。
 *
 * - `tool.execute.before`（bash）：调用 `sandbox-policy policy --cwd <dir> <command>`。
 *   `decision: "deny"`（destructive）抛错拦截；`decision: "sandbox"` 把
 *   `output.args.command` 改写为沙箱命令。策略参数取自返回的 `sandbox_argv`
 *   （`--sandbox-policy-cwd` / `--file-system-sandbox-policy` /
 *   `--network-sandbox-policy`）。`sandbox_command` 只是给人看的摘要，不能执行。
 *   opencode 的 bash 吃的是一条 shell 字符串，因此原始命令放进 `bash -c`，
 *   管道、`&&` 和重定向留在沙箱里面。
 * - `tool.execute.after`（bash）：按 call ID 回放沙箱说明，失败时附上原始命令。
 *   当前 opencode 里 after 对工具输出的修改不一定出现在界面上，所以 toast 是
 *   主要提示。
 *
 * 失败闭合：`sandbox-policy` 缺失、超时、非 0 退出或 JSON 无法解析时拒绝执行。
 * `AGENT_BEHAVIOR_DISABLE=1` 是紧急旁路，bash 原样放行。
 *
 * 依赖 PATH 上的 `sandbox-policy`（`make install-sandbox-policy`）和 `linux-sandbox`。
 * 可用 `SANDBOX_POLICY` 覆盖策略二进制路径。
 */

import type { Plugin } from "@opencode-ai/plugin";
import { spawnSync } from "node:child_process";
import path from "node:path";

type LogLevel = "debug" | "info" | "error" | "warn";

const BASH_TOOL = "bash";
const TIMEOUT_MS = 10_000;
const TOAST_DURATION_INFO_MS = 15_000;
const TOAST_DURATION_ERROR_MS = 30_000;

const FAIL_CLOSED =
  "🚫 安全策略校验失败：sandbox-policy 未能返回有效决策，已拒绝执行以避免安全策略降级。";

interface PolicyResult {
  decision?: string;
  classification?: string;
  sandbox_mode?: string;
  reason?: string;
  sandbox_summary?: string;
  sandbox_argv?: unknown;
}

interface ToolOutput {
  title: string;
  output: string;
  metadata: any;
}

/** bash 单引号转义，保证策略 JSON 和原始命令不会被外壳拆开。 */
function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function policyBin(): string {
  const raw = process.env.SANDBOX_POLICY;
  return raw && raw.trim() ? raw.trim() : "sandbox-policy";
}

function isDisabled(): boolean {
  return process.env.AGENT_BEHAVIOR_DISABLE === "1";
}

/** 已是 linux-sandbox 调用则不再包裹，避免嵌套 bwrap。 */
function isAlreadySandboxed(command: string): boolean {
  const token = command.trim().split(/\s+/, 1)[0] ?? "";
  const base = token.replace(/^['"]|['"]$/g, "");
  return base === "linux-sandbox" || base.endsWith("/linux-sandbox");
}

function flagValue(argv: string[], name: string): string | null {
  const index = argv.indexOf(name);
  if (index < 0 || index + 1 >= argv.length) return null;
  const value = argv[index + 1];
  return value.length > 0 ? value : null;
}

/**
 * 用策略 argv 里的沙箱参数包裹原始命令。
 * 不直接 exec `sandbox_argv`：那会把 `&&` / `|` 当成程序参数。
 */
function buildSandboxedCommand(argv: string[], original: string): string | null {
  const bin = argv[0];
  const cwd = flagValue(argv, "--sandbox-policy-cwd");
  const filesystem = flagValue(argv, "--file-system-sandbox-policy");
  const network = flagValue(argv, "--network-sandbox-policy");
  if (!bin || !cwd || !filesystem || !network) return null;
  return [
    shellQuote(bin),
    "--sandbox-policy-cwd",
    shellQuote(cwd),
    "--file-system-sandbox-policy",
    shellQuote(filesystem),
    "--network-sandbox-policy",
    shellQuote(network),
    "--",
    "bash",
    "-c",
    shellQuote(original),
  ].join(" ");
}

function runPolicy(cwd: string, command: string): PolicyResult | null {
  try {
    const result = spawnSync(policyBin(), ["policy", "--cwd", cwd, command], {
      encoding: "utf-8",
      timeout: TIMEOUT_MS,
      maxBuffer: 10 * 1024 * 1024,
    });
    if (result.error || result.status !== 0 || !result.stdout) return null;
    const parsed = JSON.parse(result.stdout) as PolicyResult;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function asArgv(value: unknown): string[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  if (!value.every((item) => typeof item === "string")) return null;
  return value as string[];
}

function looksFailed(output: { output: string; metadata: any }): boolean {
  const meta = output.metadata;
  if (meta && typeof meta === "object") {
    if (meta.error) return true;
    if (typeof meta.ok === "boolean" && !meta.ok) return true;
    if (typeof meta.exitCode === "number" && meta.exitCode !== 0) return true;
  }
  const text = (output.output || "").toLowerCase();
  return (
    text.includes("permission denied") ||
    text.includes("operation not permitted") ||
    text.includes("read-only file system") ||
    text.includes("seccomp") ||
    text.includes("linux-sandbox") ||
    text.includes("error:") ||
    text.includes("failed")
  );
}

function appendNote(output: ToolOutput, message: string): void {
  output.output = output.output ? `${output.output}\n\n${message}` : message;
}

function prependNote(output: ToolOutput, message: string): void {
  output.output = output.output ? `${message}\n\n${output.output}` : message;
}

export const AgentBehaviorSec: Plugin = async (ctx) => {
  const cwd = path.resolve(ctx.directory || process.cwd());
  const client = ctx.client;

  const log = (level: LogLevel, message: string): void => {
    try {
      void client?.app?.log?.({
        body: { service: "agent-behavior-sec", level, message },
      });
    } catch {
      /* logging must never affect hook behavior */
    }
  };

  const showToast = (message: string, variant: "info" | "error" = "info"): void => {
    const duration = variant === "error" ? TOAST_DURATION_ERROR_MS : TOAST_DURATION_INFO_MS;
    try {
      void client?.tui?.showToast?.({ body: { message, variant, duration } });
    } catch {
      /* toast must never affect hook behavior */
    }
  };

  const pendingNotices = new Map<string, { notice: string; original: string }>();

  return {
    "tool.execute.before": async (input, output) => {
      if (isDisabled()) return;
      if (input.tool !== BASH_TOOL) return;
      const command = output.args?.command;
      if (typeof command !== "string" || !command.trim()) return;
      if (isAlreadySandboxed(command)) return;

      const resp = runPolicy(cwd, command);
      if (!resp) {
        log("error", "sandbox-policy unavailable, blocking tool call (fail-closed)");
        showToast(FAIL_CLOSED, "error");
        throw new Error(FAIL_CLOSED);
      }

      if (resp.decision === "deny") {
        const reason = resp.reason
          ? `🚫 安全策略已阻止执行：${resp.reason}`
          : "🚫 安全策略已阻止执行。";
        log("warn", `blocked: ${reason}`);
        showToast(reason, "error");
        throw new Error(reason);
      }

      if (resp.decision !== "sandbox") {
        log("error", `unexpected decision ${String(resp.decision)}, blocking (fail-closed)`);
        showToast(FAIL_CLOSED, "error");
        throw new Error(FAIL_CLOSED);
      }

      const argv = asArgv(resp.sandbox_argv);
      const rewritten = argv ? buildSandboxedCommand(argv, command) : null;
      if (!rewritten) {
        log("error", "sandbox policy missing argv, blocking (fail-closed)");
        showToast(FAIL_CLOSED, "error");
        throw new Error(FAIL_CLOSED);
      }

      output.args.command = rewritten;
      const summary = resp.sandbox_summary ? `（${resp.sandbox_summary}）` : "";
      const notice = `🔒 已替换安全沙箱执行${summary}${resp.reason ? `\n${resp.reason}` : ""}`;
      log("info", notice);
      if (input.callID) {
        pendingNotices.set(input.callID, { notice, original: command });
      }
      showToast(notice);
    },

    "tool.execute.after": async (input, output) => {
      if (isDisabled()) return;
      if (input.tool !== BASH_TOOL) return;

      const pending = input.callID ? pendingNotices.get(input.callID) : undefined;
      if (pending && input.callID) {
        pendingNotices.delete(input.callID);
        prependNote(output, pending.notice);
        output.title = `🔒 沙箱执行: ${pending.original}`;
      }

      const ranCommand = input.args?.command;
      if (typeof ranCommand !== "string" || !ranCommand.includes("linux-sandbox")) return;
      if (!looksFailed(output)) return;

      const original = pending?.original ?? "";
      const note =
        "🔒 沙箱执行失败" +
        (original ? `\n原始命令（沙箱外重试需手动执行）: ${original}` : "");
      appendNote(output, note);
      output.title = original ? `🔒 沙箱执行失败: ${original}` : "🔒 沙箱执行失败";
      log("warn", note);
      showToast(note, "error");
    },
  };
};

export default AgentBehaviorSec;

// 行为安全插件冒烟：用真实 sandbox-policy 走 before/after。
//   SANDBOX_POLICY=sandbox-policy/.venv/bin/sandbox-policy \
//     bun opencode-plugin/behavior-security/smoke_test.ts

import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_BIN = path.resolve(HERE, "../../sandbox-policy/.venv/bin/sandbox-policy");
process.env.SANDBOX_POLICY = process.env.SANDBOX_POLICY || DEFAULT_BIN;
const POLICY_BIN = process.env.SANDBOX_POLICY;
delete process.env.AGENT_BEHAVIOR_DISABLE;

const { AgentBehaviorSec } = await import("./agent-behavior-sec.ts");

const toasts: string[] = [];
const ctx: any = {
  directory: "/workspace",
  client: {
    app: { log: () => {} },
    tui: {
      showToast: (req: { body?: { message?: string } }) => {
        if (req?.body?.message) toasts.push(req.body.message);
      },
    },
  },
};

let pass = 0;
let fail = 0;
function check(name: string, cond: boolean, extra?: string) {
  if (cond) {
    pass++;
    console.log(`  PASS: ${name}`);
  } else {
    fail++;
    console.log(`  FAIL: ${name}${extra ? " — " + extra : ""}`);
  }
}

function bashOutput(command: string) {
  return { args: { command } };
}

async function main() {
  const hooks = await AgentBehaviorSec(ctx);
  const before = hooks["tool.execute.before"]!;
  const after = hooks["tool.execute.after"]!;

  console.log("[before] destructive -> deny");
  {
    toasts.length = 0;
    const output = bashOutput("rm -rf /");
    let threw = false;
    let message = "";
    try {
      await before({ tool: "bash", sessionID: "s", callID: "deny" } as any, output);
    } catch (err) {
      threw = true;
      message = err instanceof Error ? err.message : String(err);
    }
    check("throws", threw);
    check("command unchanged", output.args.command === "rm -rf /", output.args.command);
    check("reason mentions block", message.includes("阻止"), message);
    check("toast", toasts.some((item) => item.includes("阻止")));
  }

  console.log("[before] safe -> read-only sandbox via bash -c");
  {
    const output = bashOutput("ls -la");
    await before({ tool: "bash", sessionID: "s", callID: "safe" } as any, output);
    const command = String(output.args.command);
    check("wrapped", command.includes("linux-sandbox") && command.includes("bash -c"), command);
    check("original inside -c", command.includes("bash -c 'ls -la'"), command);
    check("read-only policy", command.includes('"kind":"root"') && !command.includes("current_working_directory"), command);
    check("network restricted", command.includes(`--network-sandbox-policy '"restricted"'`), command);
  }

  console.log("[before] dangerous -> workspace-write");
  {
    const output = bashOutput("chmod 644 file");
    await before({ tool: "bash", sessionID: "s", callID: "danger" } as any, output);
    const command = String(output.args.command);
    check("cwd write", command.includes("current_working_directory"), command);
    check("bash -c keeps command", command.includes("bash -c 'chmod 644 file'"), command);
  }

  console.log("[before] default network command");
  {
    const output = bashOutput("curl https://example.com");
    await before({ tool: "bash", sessionID: "s", callID: "net" } as any, output);
    const command = String(output.args.command);
    check("network enabled", command.includes(`--network-sandbox-policy '"enabled"'`), command);
  }

  console.log("[before] chain stays inside bash -c");
  {
    const output = bashOutput("echo hello && ls");
    await before({ tool: "bash", sessionID: "s", callID: "chain" } as any, output);
    const command = String(output.args.command);
    check("operators quoted", command.endsWith("bash -c 'echo hello && ls'"), command);
  }

  console.log("[before] quote in command is escaped");
  {
    const output = bashOutput("echo 'a b'");
    await before({ tool: "bash", sessionID: "s", callID: "quote" } as any, output);
    const command = String(output.args.command);
    const quoted = "bash -c 'echo " + "'\\''" + "a b" + "'\\''" + "'";
    check("single quote escaped", command.includes(quoted), command);
  }

  console.log("[before] non-bash / empty / already sandboxed");
  {
    const read = { args: { command: "cat /etc/passwd" } };
    await before({ tool: "read", sessionID: "s", callID: "read" } as any, read);
    check("read ignored", read.args.command === "cat /etc/passwd");

    const empty = bashOutput("   ");
    await before({ tool: "bash", sessionID: "s", callID: "empty" } as any, empty);
    check("empty ignored", empty.args.command === "   ");

    const nested = bashOutput("linux-sandbox -- echo hi");
    await before({ tool: "bash", sessionID: "s", callID: "nested" } as any, nested);
    check("already sandboxed", nested.args.command === "linux-sandbox -- echo hi");
  }

  console.log("[after] replay notice, then failure");
  {
    toasts.length = 0;
    const ran = "linux-sandbox -- bash -c 'ls -la'";
    const output: any = { title: "", output: "permission denied", metadata: {} };
    await after(
      { tool: "bash", sessionID: "s", callID: "safe", args: { command: ran } } as any,
      output,
    );
    check("notice prepended", String(output.output).includes("已替换安全沙箱执行"), output.output);
    check("failure title", String(output.title).includes("沙箱执行失败"), output.title);
    check("original command", String(output.output).includes("ls -la"), output.output);
    check("failure toast", toasts.some((item) => item.includes("沙箱执行失败")));
  }

  console.log("[before] missing binary -> fail closed");
  {
    process.env.SANDBOX_POLICY = "/no/such/sandbox-policy";
    const output = bashOutput("ls");
    let threw = false;
    try {
      await before({ tool: "bash", sessionID: "s", callID: "missing" } as any, output);
    } catch {
      threw = true;
    }
    check("throws", threw);
    check("command unchanged", output.args.command === "ls");
    process.env.SANDBOX_POLICY = POLICY_BIN;
  }

  console.log("[before] disable bypass");
  {
    process.env.AGENT_BEHAVIOR_DISABLE = "1";
    process.env.SANDBOX_POLICY = POLICY_BIN;
    const output = bashOutput("rm -rf /");
    let threw = false;
    try {
      await before({ tool: "bash", sessionID: "s", callID: "off" } as any, output);
    } catch {
      threw = true;
    }
    check("does not throw", !threw);
    check("command unchanged", output.args.command === "rm -rf /");
    delete process.env.AGENT_BEHAVIOR_DISABLE;
  }

  console.log(`\n${pass} passed, ${fail} failed`);
  if (fail > 0) process.exit(1);
}

await main();

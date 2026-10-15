# Agent 行为安全 opencode 插件

本插件把 [`sandbox-policy/`](../../sandbox-policy/) 的命令分类和沙箱策略接到 opencode 钩子上，不在这里重写规则。

入口文件：

```text
opencode-plugin/behavior-security/agent-behavior-sec.ts
```

`make install-behavior-plugin` 会把它复制为 `~/.config/opencode/plugins/agent-behavior-sec.ts`。

## 策略从哪来

`sandbox-policy/` 是独立的 Python 包。在 `agent-security/` 下执行 `make install-sandbox-policy` 后，插件调用 PATH 上的 `sandbox-policy`：

| 命令 | 作用 |
| --- | --- |
| `sandbox-policy policy --cwd <dir> <command>` | 插件实际调用的入口。`destructive` 返回 `deny`，其余返回 `sandbox` 和 `linux-sandbox` 参数 |
| `sandbox-policy classify` | 同一套四层分类，供人工查看 |
| `src/sandbox_policy/rules.py` / `rules.yaml` | 内置规则与用户扩展（冲突时以内置规则为准） |

规则变更改 `sandbox-policy/`，不要把 Python 策略复制进本目录。

## 钩子

只处理 `bash`。空命令直接放行。命令已经以 `linux-sandbox` 开头时不再包裹，避免嵌套 bwrap。

| 事件 | 行为 |
| --- | --- |
| `tool.execute.before` | 调用 `sandbox-policy policy`。`deny` 抛错拦截。`sandbox` 把 `output.args.command` 改写为沙箱命令。策略程序不可用、超时或返回无法解析时拒绝执行。 |
| `tool.execute.after` | 回放沙箱说明。沙箱命令失败时附上原始命令。toast 是主要提示。 |

改写使用 `sandbox_argv` 里的策略参数，原始命令放进 `bash -c`，管道和 `&&` 留在沙箱内。`sandbox_command` 隐藏了策略 JSON，不能执行。

```text
linux-sandbox --sandbox-policy-cwd '<cwd>' \
  --file-system-sandbox-policy '<json>' \
  --network-sandbox-policy '<json>' \
  -- bash -c '<原始命令>'
```

分类与沙箱模式由 `sandbox-policy` 决定：

| 分类 | 插件行为 |
| --- | --- |
| `destructive` | 拒绝执行 |
| `safe` | 只读沙箱，网络关闭 |
| `dangerous` / `default` | workspace-write。网络和额外写路径由策略给出 |

`sudo` 整条命令按 `sandbox-policy` 的分类处理，插件不剥前缀。

## 环境变量

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `SANDBOX_POLICY` | `sandbox-policy` | 策略二进制路径 |
| `AGENT_BEHAVIOR_DISABLE` | 未设置 | `1` 时紧急旁路，bash 原样放行 |

单次策略调用超时 10 秒。运行改写后的命令还需要 PATH 上的 `linux-sandbox`。

## 冒烟

```bash
SANDBOX_POLICY=sandbox-policy/.venv/bin/sandbox-policy \
  bun opencode-plugin/behavior-security/smoke_test.ts
```

# witty-sandboxer

Sandbox launcher for local coding agents. It classifies shell commands, then runs them inside a Linux process sandbox, and can also hand the agent a container sandbox for stronger isolation.

面向本地 Agent 运行时的沙箱启动器。对 Agent 发出的 shell 命令做分类，再放进 Linux 进程沙箱执行；需要更强隔离时，通过 OpenSandbox 提供容器级原语。

## 它解决什么问题

编码 Agent 会在本机执行 `bash`。同一条命令可能是只读查看，也可能是删系统目录或写块设备。witty-sandboxer 把这件事拆成两层，互不抢同一条执行路径：

| 层 | 目录 | 做什么 |
| --- | --- | --- |
| 行为策略 | [`agent-security/`](agent-security/) | 分类命令，拒绝毁灭性操作，为其余命令生成 `linux-sandbox` 参数 |
| 隔离运行时 | [`agent-sandbox/`](agent-sandbox/) | 用 bubblewrap + seccomp 执行进程沙箱，或用 OpenSandbox 容器执行 |

策略只回答「这条命令以什么权限跑」。沙箱只回答「这些权限如何落到内核隔离上」。OpenCode 插件是接入层，把两层挂到本地 Agent 工作流。

## 架构

```text
OpenCode bash
    │
    ▼
agent-behavior-sec          tool.execute.before
    │
    ▼
sandbox-policy              classify + policy
    │
    ├── destructive ──► deny
    └── safe / dangerous / default
            │
            ▼
        linux-sandbox
            ├── bubblewrap   文件系统、PID / user 命名空间
            └── seccomp      网络系统调用、ptrace、io_uring、NO_NEW_PRIVS


OpenCode agent
    │
    ▼
agent-sandbox-infra         7 个容器原语
    │
    ▼
sandbox_runner.py ──► OpenSandbox SDK ──► 容器
```

两条路径职责分开：行为安全插件改写 `bash`；容器插件注册独立工具，不挂 `tool.execute.before`。

## 能力

**进程沙箱（`linux-sandbox`）**

- 文件系统默认只读，按策略开放工作目录、`/tmp` 或指定绝对路径的写权限。
- 可写根下的 `.git`、`.agents`、`.copilot-shell` 仍保持只读，降低符号链接替换受保护路径的可能。
- 网络关闭时，seccomp 拒绝 `connect`、`accept`、`bind` 等调用，仅放行 `AF_UNIX`；同时无条件拒绝 `ptrace` 与 `io_uring_*`。
- 支持代理路由模式：流量经隔离网络命名空间里的本地桥转发，并收紧 socket 地址族。
- 启用限制时设置 `PR_SET_NO_NEW_PRIVS`。
- 单目录自包含，可单独拷贝后用 `make build` 编译。

**命令策略（`sandbox-policy`）**

四层分类，优先级从高到低：

| 分类 | 决定 | 沙箱 |
| --- | --- | --- |
| `destructive` | 拒绝执行 | 不进入沙箱 |
| `dangerous` | 允许执行 | 工作目录与 `/tmp` 可写，网络关闭，不自动补权限 |
| `safe` | 允许执行 | 只读，网络关闭 |
| `default` | 允许执行 | 工作目录与 `/tmp` 可写；仅此层可按规则补网络或额外写路径 |

内置规则覆盖磁盘分区与格式化、关机重启、删除系统关键目录、向块设备 `dd`、杀死 init、fork bomb，以及 `rm -rf`、`chmod`、`chown`、`sudo` 等危险命令。`cargo`、`npm`、`pip`、`git clone/fetch/pull/push`、`curl`、`wget` 等在 `default` 层可获得网络权限。用户扩展写在 `rules.yaml`，与内置规则冲突时以内置规则为准。

策略程序不可用、超时或输出无法解析时，行为安全插件拒绝执行。

**容器沙箱（OpenSandbox）**

插件向 Agent 暴露七个可组合原语：`sandbox_create`、`sandbox_exec`、`sandbox_upload`、`sandbox_upload_text`、`sandbox_download`、`sandbox_download_dir`、`sandbox_destroy`。Python runner 对每个原语输出一行 JSON。镜像准备脚本拉取 `opensandbox/code-interpreter:v1.1.0` 与 `opensandbox/execd:v1.1.0`。

## 仓库结构

```text
witty-sandboxer/
├── agent-sandbox/
│   ├── process-sandbox/          # linux-sandbox（Rust）
│   ├── opencode-plugin/          # OpenSandbox 容器插件
│   └── sandbox-image/docker/     # Docker / moby 与镜像准备
└── agent-security/
    ├── sandbox-policy/           # 分类与策略生成（Python）
    └── opencode-plugin/          # OpenCode 行为安全插件
```

| 路径 | 说明 |
| --- | --- |
| [`agent-sandbox/process-sandbox/`](agent-sandbox/process-sandbox/) | bubblewrap + seccomp，产物 `linux-sandbox` |
| [`agent-sandbox/opencode-plugin/`](agent-sandbox/opencode-plugin/) | OpenCode 容器控制插件与 `sandbox_runner.py` |
| [`agent-sandbox/sandbox-image/docker/`](agent-sandbox/sandbox-image/docker/) | 安装 moby 并拉取沙箱镜像 |
| [`agent-security/sandbox-policy/`](agent-security/sandbox-policy/) | `sandbox-policy classify` / `sandbox-policy policy` |
| [`agent-security/opencode-plugin/`](agent-security/opencode-plugin/) | 在 `tool.execute.before` 改写 bash |

本仓库集成上游 OpenSandbox SDK，不内置其 server、Kubernetes operator 或 microVM 运行时。

## 环境要求

| 组件 | 要求 |
| --- | --- |
| `linux-sandbox` | Linux（用户命名空间可用）、bubblewrap（`bwrap`）、Rust 1.93.0（由 `rust-toolchain.toml` 固定） |
| `sandbox-policy` | Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)、PyYAML |
| OpenCode 插件 | OpenCode；行为安全插件的冒烟测试需要 [bun](https://bun.sh) |
| 容器沙箱 | Python ≥ 3.10、`opensandbox` SDK、可用的 Docker，以及 `OPENSANDBOX_API_KEY` 或 SDK 配置 |

```bash
# openEuler / RHEL
sudo dnf install -y bubblewrap
# Debian / Ubuntu
sudo apt install bubblewrap
```

## 快速开始

### 1. 构建进程沙箱

```bash
cd agent-sandbox/process-sandbox
make build          # cargo build --release，产物 target/release/linux-sandbox
sudo make install PREFIX=/usr/local
linux-sandbox --help
```

只读执行：

```bash
linux-sandbox \
  --sandbox-policy-cwd "$(pwd)" \
  --file-system-sandbox-policy '{"kind":"restricted","entries":[{"path":{"type":"special","value":{"kind":"root"}},"access":"read"}]}' \
  --network-sandbox-policy '"restricted"' \
  -- cat /etc/hostname
```

工作目录可写、其余路径只读：

```bash
linux-sandbox \
  --sandbox-policy-cwd /tmp/workspace \
  --file-system-sandbox-policy '{"kind":"restricted","entries":[{"path":{"type":"special","value":{"kind":"root"}},"access":"read"},{"path":{"type":"special","value":{"kind":"current_working_directory"}},"access":"write"}]}' \
  --network-sandbox-policy '"restricted"' \
  -- bash -c 'echo hello > /tmp/workspace/test.txt'
```

更多示例见 [`agent-sandbox/process-sandbox/README.md`](agent-sandbox/process-sandbox/README.md)。

### 2. 安装命令策略

```bash
cd agent-security
make install-sandbox-policy
# 将 sandbox-policy 软链到 ~/.local/bin，并把该目录写入 ~/.bashrc

sandbox-policy classify "git status"
sandbox-policy classify --json "rm -rf /"
sandbox-policy policy --cwd /workspace "git status"
```

`make install-sandbox-policy` 以可编辑方式安装。修改 [`rules.yaml`](agent-security/sandbox-policy/src/sandbox_policy/rules.yaml) 后立即生效。卸载：

```bash
make uninstall-sandbox-policy
```

### 3. 接入 OpenCode 行为安全

需要 PATH 上同时有 `sandbox-policy` 与 `linux-sandbox`。

```bash
cd agent-security
make install-plugin
# 复制到 ~/.config/opencode/plugins/agent-behavior-sec.ts
```

重启 OpenCode。此后 `bash` 工具会先经策略：

- `destructive`：抛错拦截。
- 其余分类：把命令改写为 `linux-sandbox ... -- bash -c '<原始命令>'`，管道和 `&&` 留在沙箱内。
- 命令已经以 `linux-sandbox` 开头时不再包裹。

紧急旁路：`AGENT_BEHAVIOR_DISABLE=1`。策略程序路径：`SANDBOX_POLICY`（默认 `sandbox-policy`）。单次策略调用超时 10 秒。

### 4. 接入容器沙箱（可选）

```bash
# 安装 Docker 并拉取 OpenSandbox 镜像（需要 root 与公网）
sudo bash agent-sandbox/sandbox-image/docker/setup-docker.sh

pip install opensandbox
cd agent-sandbox/opencode-plugin
make install-global
```

重启 OpenCode 后，Agent 可以组合七个工具，例如：创建 `python:3.12` 沙箱、上传脚本、执行、下载结果、销毁沙箱。不经过 OpenCode 时，可直接调用 runner：

```bash
python3 sandbox_runner.py create --image python:3.12
python3 sandbox_runner.py exec --sandbox-id sb-xxx --command "echo hello"
python3 sandbox_runner.py destroy --sandbox-id sb-xxx
```

## 扩展规则

在 [`agent-security/sandbox-policy/src/sandbox_policy/rules.yaml`](agent-security/sandbox-policy/src/sandbox_policy/rules.yaml) 追加规则。可扩展的段：

| 段 | 作用 |
| --- | --- |
| `destructive` | 直接拒绝。需要 `command`、`command_prefix` 或 `pattern`，以及 `reason` |
| `dangerous` | 进沙箱，禁止自动补权限 |
| `safe_commands` / `safe_commands_linux` | 无条件只读 |
| `safe_conditional` | 只读，但命中 `deny_args` 时降级 |
| `permissions` | 仅 `default` 命令可自动补 `network` 或 `write_paths` |
| `shell_unsafe_operators` / `shell_safe_operators` | 控制 `bash -c` 能否按安全链式命令拆分 |

内置规则已经占用的命令名、前缀和 pattern 会忽略 yaml 中的同名条目，并在 stderr 提示。此文件不能删除或改写内置规则。

## 开发与测试

```bash
# 进程沙箱：单元测试与集成测试（跳过需要特权的 bwrap_seccomp）
cd agent-sandbox/process-sandbox && make test

# 进程沙箱端到端（需已安装 linux-sandbox）
python3 tests/integration_test.py

# 策略包
cd agent-security/sandbox-policy && uv run pytest

# 行为安全插件冒烟
cd agent-security && \
  SANDBOX_POLICY=sandbox-policy/.venv/bin/sandbox-policy \
  bun opencode-plugin/behavior-security/smoke_test.ts

# 容器插件冒烟（需要 bun）
cd agent-sandbox/opencode-plugin && make smoke
```

打包进程沙箱：

```bash
cd agent-sandbox/process-sandbox
make package        # dist/process-sandbox-<version>.tar.gz
```

## 安全边界

这套机制约束的是 Agent 经策略进入沙箱的命令：文件系统视图、网络系统调用和提权标志。分类基于命令拆分与规则匹配，复杂 shell 语法、解释器内部执行和已授予网络后的出站行为，仍取决于对应规则是否覆盖。容器路径的隔离强度由 OpenSandbox 与底层容器运行时决定。


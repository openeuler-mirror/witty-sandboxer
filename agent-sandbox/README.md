# agent-sandbox

`agent-sandbox` 是 kylin-agent-sdk 中的沙箱子工程集合，按隔离粒度与运行形态划分为三类组件，并配套 opencode 插件层：

```
agent-sandbox/
├── process-sandbox/    # 进程沙箱
├── opensandbox/        # 异构沙箱（上游 OpenSandbox 项目）
├── sandbox-image/      # 沙箱镜像（容器镜像、microVM 镜像等）
└── opencode-plugin/    # opencode 插件（接入上述沙箱到 opencode 工作流）
```

## 子组件

| 目录                                       | 组件          | 说明                                                                                                                                                                         |
| ---------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`process-sandbox/`](./process-sandbox/) | 进程沙箱        | 基于 bubblewrap + seccomp 的独立 Linux 进程沙箱，产出 `linux-sandbox` 二进制；目录自包含，可单独拷贝编译。Fork from：https://github.com/agentic-os-org/ANOLISA/tree/main/src/agent-sec-core/linux-sandbox |
| [`opensandbox/`](./opensandbox/)         | 异构沙箱        | Fork from：https://github.com/opensandbox-group/OpenSandbox 。提供 Docker / Kubernetes / Firecracker microVM 异构沙箱平台，含 SDK、CLI、server、k8s operator 等。                           |
| [`sandbox-image/`](./sandbox-image/)     | 沙箱镜像        | 为上述沙箱运行构建与分发的各类镜像，含容器镜像、microVM 镜像等（预留，待补充）。                                                                                                                               |
| [`opencode-plugin/`](./opencode-plugin/) | opencode 插件 | 将上述沙箱接入 opencode 工作流的插件层。当前含 `agent-sandbox-infra.ts`（OpenSandbox 容器控制插件，8 个可组合工具原语 + 1 个 CSV 分析预设流水线）与配套的 `sandbox_runner.py` Python runner。                              |

## 关系说明

- **进程沙箱** 是最轻量的隔离层，单机命令级；`agent-security` 的行为安全插件通过 PATH 上的 `linux-sandbox` 二进制调用它。
- **异构沙箱** 是平台级隔离，支持集群、microVM、强隔离运行时（gVisor / Kata / Firecracker），面向 Coding Agent、GUI Agent、评测、RL 训练等负载。
- **沙箱镜像** 为异构沙箱与上层 Agent 提供可分发的运行环境镜像，覆盖容器镜像与 microVM 镜像等多种形态。
- **opencode 插件** 是接入层，把上述沙箱能力挂到 opencode 钩子（如 `tool.execute.before`）上；与 `agent-security/opencode-plugin/` 的行为安全插件职责互补，避免在同一条 bash 上抢钩子。

## 备注

- `opensandbox/` 为上游项目 衍生，遵循上游贡献流程。
- `process-sandbox/` 在本仓维护后续修改。它是 ANOLISA `linux-sandbox` 的衍生代码，再上游是 OpenAI Codex。单独分发时带上该目录的 `LICENSE` 和 `NOTICE`。

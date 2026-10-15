# Makefile 使用手册

`agent-security/Makefile` 用于安装/卸载 `sandbox-policy`，以及部署行为安全 opencode 插件。

## 命令一览

| 命令 | 说明 |
| --- | --- |
| `make install-sandbox-policy` | 安装 `sandbox-policy`（`uv sync`，命令 `sandbox-policy`） |
| `make uninstall-sandbox-policy` | 卸载 `sandbox-policy`（移除 `.venv`） |
| `make install-plugin` | 安装行为安全 opencode 插件到 `$(PLUGIN_DIR)` |
| `make install-behavior-plugin` | 安装行为安全插件 |
| `make uninstall-plugin` | 移除行为安全插件，并清理已删除的内容安全插件 |
| `make uninstall-behavior-plugin` | 只卸载行为安全插件 |
| `make help` | 查看目标说明 |

## 可覆盖变量

| 变量 | 默认值 | 用法示例 |
| --- | --- | --- |
| `UV` | `uv` | `make install-sandbox-policy UV=/opt/bin/uv` |
| `INSTALL_BIN` | `~/.local/bin` | `make install-sandbox-policy INSTALL_BIN=/usr/local/bin` |
| `PLUGIN_DIR` | `~/.config/opencode/plugins` | `make install-plugin PLUGIN_DIR=/x` |
| `DESTDIR` | （空） | `make install-plugin DESTDIR=/tmp/root` |

## 安装 sandbox-policy

行为安全用命令分类和 `linux-sandbox` 策略。`sandbox-policy` 是独立的 Python 包，运行时依赖只有 `PyYAML`。

```bash
make install-sandbox-policy
```

`make install-sandbox-policy` 在 `sandbox-policy/.venv` 里执行 `uv sync`，把 `sandbox-policy` 软链到 `~/.local/bin`，并把该目录写入 `~/.bashrc` 的 `PATH`。装完后：

```bash
sandbox-policy classify "git status"
sandbox-policy classify --json "rm -rf /"
sandbox-policy policy --cwd /workspace "git status"
```

用户扩展写在 `sandbox-policy/src/sandbox_policy/rules.yaml`。安装是可编辑模式，改这个文件会立即生效；与内置规则冲突的条目会被忽略。

```bash
make uninstall-sandbox-policy   # 移除 sandbox-policy/.venv 与软链
```

测试：

```bash
cd sandbox-policy && uv run pytest
```

## 安装 opencode 插件

```bash
make install-plugin                                              # 安装行为安全插件
make install-plugin PLUGIN_DIR=~/.local/share/opencode/plugins  # 自定义目录
make install-plugin DESTDIR=/tmp/root                            # 指定 staged 根目录
```

安装后请**重启 opencode** 以加载插件。

## 卸载 opencode 插件

```bash
make uninstall-plugin            # 移除行为安全插件，并清掉已删除的内容安全插件
make uninstall-behavior-plugin   # 只卸载行为安全插件
```

`make uninstall-plugin` 还会删除以前安装留下的 `agent-content-sec.ts` 和 `agent-sec-plugin.ts`。卸载后请**重启 opencode** 以生效。

## 说明

- 行为安全入口：`opencode-plugin/behavior-security/agent-behavior-sec.ts` → `<PLUGIN_DIR>/agent-behavior-sec.ts`
- opencode 启动时会自动加载插件目录下的文件，因此安装/卸载后均需重启 opencode。
- 插件说明见 `opencode-plugin/README.md` 与 `opencode-plugin/behavior-security/README.md`。

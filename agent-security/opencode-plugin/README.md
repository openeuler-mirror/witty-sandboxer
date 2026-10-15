# opencode 插件

行为安全插件放在本目录，入口文件一个。opencode 按文件加载，安装时只复制入口 `.ts`，文件名保持不变。

| 插件 | 职责 | 源文件 | 安装后 |
| --- | --- | --- | --- |
| 行为安全 | 命令分类与 linux-sandbox 策略 | `behavior-security/agent-behavior-sec.ts` | `~/.config/opencode/plugins/agent-behavior-sec.ts` |

策略逻辑放在 [`sandbox-policy/`](../sandbox-policy/)，用 `make install-sandbox-policy` 安装，不要复制进插件目录。说明见 [`behavior-security/README.md`](behavior-security/README.md)。

行为安全负责命令是否执行、以及以何种沙箱执行，钩子落在 `tool.execute.before`。

## 安装 / 卸载

在 `agent-security/` 下执行：

```bash
make install-plugin             # 安装行为安全插件
make install-behavior-plugin    # 同上
make uninstall-plugin           # 移除行为安全插件，并清掉已删除的内容安全插件
```

`PLUGIN_DIR` 默认 `~/.config/opencode/plugins`，可用 `DESTDIR` 做 staged 安装。安装或卸载后重启 opencode。

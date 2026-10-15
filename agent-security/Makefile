.PHONY: install-sandbox-policy uninstall-sandbox-policy \
        install-plugin uninstall-plugin \
        install-behavior-plugin uninstall-behavior-plugin help

UV         ?= uv

# sandbox-policy：独立的纯 Python 包，只依赖 PyYAML。
SANDBOX_DIR := sandbox-policy
SANDBOX_VENV_BIN := $(abspath $(SANDBOX_DIR)/.venv/bin)

# 软链入口目录：只把最终 CLI 命令软链到这里，而非把整个 venv/bin 暴露到 PATH。
# 默认使用 ~/.local/bin（XDG 用户级 bin）。安装时幂等写入 ~/.bashrc。
# 可通过 `make install-sandbox-policy INSTALL_BIN=/usr/local/bin` 覆盖为系统级安装。
INSTALL_BIN ?= $(HOME)/.local/bin
export PATH := $(INSTALL_BIN):$(PATH)

# 片段放在非交互 return 之前，用户在当前终端 source ~/.bashrc 时即可生效。
# 卸载不删这条，避免影响其它用户级工具。
define ensure_install_bin_path
bin="$(INSTALL_BIN)"; \
rc="$(HOME)/.bashrc"; \
marker="# agent-security: $$bin"; \
touch "$$rc"; \
if grep -Fqx "$$marker" "$$rc"; then \
	echo "[path] $$bin 已在 $$rc 的 PATH 中"; \
else \
	tmp=$$(mktemp); \
	{ \
		printf '%s\ncase ":%s:" in\n  *":%s:"*) ;;\n  *) export PATH="%s:$$PATH" ;;\nesac\n\n' \
			"$$marker" '$$PATH' "$$bin" "$$bin"; \
		cat "$$rc"; \
	} > "$$tmp"; \
	cat "$$tmp" > "$$rc"; \
	rm -f "$$tmp"; \
	echo "[path] 已将 $$bin 写入 $$rc"; \
	echo "[path] 当前终端执行: source $$rc"; \
fi
endef

# opencode 插件：行为安全一个入口，安装后文件名保持不变。
PLUGIN_DIR  ?= $(HOME)/.config/opencode/plugins
BEHAVIOR_PLUGIN_SRC  := opencode-plugin/behavior-security/agent-behavior-sec.ts
BEHAVIOR_PLUGIN_FILE := agent-behavior-sec.ts
# 已删除的内容安全插件。卸载时清掉这些旧安装，避免 opencode 继续加载。
REMOVED_PLUGIN_FILES := agent-content-sec.ts agent-sec-plugin.ts

help:
	@echo "agent-security Makefile"
	@echo ""
	@echo "  make install-sandbox-policy      安装 sandbox-policy（uv sync，命令 sandbox-policy）"
	@echo "  make uninstall-sandbox-policy    卸载 sandbox-policy（移除 .venv）"
	@echo "  make install-plugin              安装行为安全 opencode 插件"
	@echo "  make install-behavior-plugin     安装行为安全插件"
	@echo "  make uninstall-plugin            移除行为安全插件，并清理已删除的内容安全插件"
	@echo "  make uninstall-behavior-plugin   卸载行为安全插件"

# sandbox-policy 只有 PyYAML。可编辑安装后，改 rules.yaml 会立即生效。
install-sandbox-policy:
	cd $(SANDBOX_DIR) && $(UV) sync
	@mkdir -p $(INSTALL_BIN)
	@ln -sfn "$(SANDBOX_VENV_BIN)/sandbox-policy" "$(INSTALL_BIN)/sandbox-policy"
	@echo "[install-sandbox-policy] 软链 sandbox-policy -> $(SANDBOX_VENV_BIN)/sandbox-policy"
	@echo "[install-sandbox-policy] 完成。可执行入口:"
	@echo "  $(INSTALL_BIN)/sandbox-policy"
	@$(ensure_install_bin_path)

uninstall-sandbox-policy:
	@rm -rf $(SANDBOX_DIR)/.venv
	@rm -f $(INSTALL_BIN)/sandbox-policy
	@echo "[uninstall-sandbox-policy] 已移除 $(SANDBOX_DIR)/.venv 与软链 $(INSTALL_BIN)/sandbox-policy"

# --- opencode 插件 ---
install-plugin: install-behavior-plugin
	@echo "[install-plugin] 请重启 opencode 以加载插件。"

install-behavior-plugin:
	@mkdir -p $(DESTDIR)$(PLUGIN_DIR)
	install -m 0644 $(BEHAVIOR_PLUGIN_SRC) $(DESTDIR)$(PLUGIN_DIR)/$(BEHAVIOR_PLUGIN_FILE)
	@echo "[install-behavior-plugin] 已安装 -> $(DESTDIR)$(PLUGIN_DIR)/$(BEHAVIOR_PLUGIN_FILE)"

uninstall-behavior-plugin:
	@rm -f $(DESTDIR)$(PLUGIN_DIR)/$(BEHAVIOR_PLUGIN_FILE)
	@echo "[uninstall-behavior-plugin] 已移除 $(DESTDIR)$(PLUGIN_DIR)/$(BEHAVIOR_PLUGIN_FILE)"

uninstall-plugin: uninstall-behavior-plugin
	@for f in $(REMOVED_PLUGIN_FILES); do \
		rm -f $(DESTDIR)$(PLUGIN_DIR)/$$f; \
		echo "[uninstall-plugin] 已清理 $$f（若存在）"; \
	done
	@echo "[uninstall-plugin] 请重启 opencode 以生效。"

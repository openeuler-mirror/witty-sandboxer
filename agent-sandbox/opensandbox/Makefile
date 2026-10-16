# Makefile for OpenSandbox (server + CLI) source install/uninstall
#
# 用法:
#   make install          # 安装 server + cli 依赖，软链入口命令到 BINDIR
#   make install-server   # 仅安装 server
#   make install-cli      # 仅安装 cli (osb/opensandbox/kysandbox)
#   make uninstall        # 卸载软链 (保留 .venv)
#   make uninstall-full   # 卸载软链 + 删除 .venv
#   make clean            # 删除两个 .venv
#   make server           # 前台启动 server (Ctrl+C 停止)
#   make server-bg        # 后台启动 server (nohup)
#   make server-stop      # 停止后台 server
#   make check            # 验证安装
#   make config           # 生成 ~/.sandbox.toml (若不存在)
#
# 可覆盖变量示例:
#   make install BINDIR=/usr/local/bin UV=/path/to/uv

SHELL := /bin/bash

# ---- 路径与工具 ----
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SERVER_DIR := $(ROOT_DIR)/server
CLI_DIR := $(ROOT_DIR)/cli
SDK_DIR := $(ROOT_DIR)/sdks/sandbox/python

# uv 解析: 优先 PATH 上的 uv，其次 ~/.local/bin/uv
UV ?= $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
# python 解析: 依次回退 python3.12 -> python3.11 -> python3.10 -> python3，避免不同 OS 环境下版本缺失
PYTHON ?= $(shell \
	for v in python3.12 python3.11 python3.10 python3; do \
		p=$$(command -v $$v 2>/dev/null); \
		if [ -n "$$p" ]; then printf '%s' "$$v"; exit 0; fi; \
	done; printf '%s' python3)

# 软链安装目录
BINDIR ?= $(HOME)/.local/bin

# 入口命令名
SERVER_BIN := opensandbox-server
CLI_BINS := osb opensandbox kysandbox

# 配置文件
SANDBOX_CONFIG := $(HOME)/.sandbox.toml

# 日志
SERVER_LOG ?= $(HOME)/.opensandbox.log

# 颜色
C_CYAN := \033[36m
C_GREEN := \033[32m
C_YELLOW := \033[33m
C_RED := \033[31m
C_RESET := \033[0m

# ---- 默认目标 ----
.PHONY: help
help:
	@printf "$(C_CYAN)OpenSandbox Makefile$(C_RESET)\n"
	@printf "  install          安装 server + cli + sdk 依赖并软链入口命令\n"
	@printf "  install-server   仅安装 server\n"
	@printf "  install-cli      仅安装 cli (osb/opensandbox/kysandbox)\n"
	@printf "  install-sdk      仅安装 sdk (opensandbox python 包, 可编辑安装到 $(PYTHON))\n"
	@printf "  uninstall        卸载软链 + 从系统 python 移除可编辑包 (保留 .venv)\n"
	@printf "  uninstall-full   卸载软链 + 移除可编辑包 + 删除 .venv\n"
	@printf "  clean            删除三个 .venv\n"
	@printf "  server           前台启动 server\n"
	@printf "  server-bg        后台启动 server (nohup)\n"
	@printf "  server-stop     停止后台 server\n"
	@printf "  check            验证安装\n"
	@printf "  config           生成 ~/.sandbox.toml (若不存在)\n"
	@printf "\n变量: UV=$(UV) BINDIR=$(BINDIR) PYTHON=$(PYTHON)\n"

# ---- 工具检查 ----
.PHONY: check-uv
check-uv:
	@if [ ! -x "$(UV)" ]; then \
		printf "$(C_RED)错误: 找不到 uv (尝试 $(UV))$(C_RESET)\n"; \
		printf "请先安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh\n"; \
		exit 1; \
	fi

# ---- 安装 ----
.PHONY: install install-server install-cli install-sdk

install: install-server install-cli install-sdk
	@printf "$(C_GREEN)✓ 全部安装完成$(C_RESET)\n"
	@printf "入口命令: $(BINDIR)/$(SERVER_BIN) $(foreach b,$(CLI_BINS),$(BINDIR)/$(b))\n"
	@printf "SDK 可导入: $(PYTHON) -c 'import opensandbox; print(opensandbox.__version__)'\n"
	@printf "启动 server: make server-bg\n"

install-server: check-uv
	@printf "$(C_CYAN)→ 同步 server 依赖$(C_RESET)\n"
	@cd "$(SERVER_DIR)" && "$(UV)" sync --all-groups
	@printf "$(C_CYAN)→ 软链 $(SERVER_BIN) -> $(BINDIR)/$(SERVER_BIN)$(C_RESET)\n"
	@mkdir -p "$(BINDIR)"
	@ln -sf "$(SERVER_DIR)/.venv/bin/$(SERVER_BIN)" "$(BINDIR)/$(SERVER_BIN)"

install-cli: check-uv
	@printf "$(C_CYAN)→ 同步 cli 依赖$(C_RESET)\n"
	@cd "$(CLI_DIR)" && "$(UV)" sync
	@printf "$(C_CYAN)→ 软链 cli 入口 -> $(BINDIR)/$(C_RESET)\n"
	@mkdir -p "$(BINDIR)"
	@$(foreach b,$(CLI_BINS),ln -sf "$(CLI_DIR)/.venv/bin/$(b)" "$(BINDIR)/$(b)";)

install-sdk: check-uv
	@printf "$(C_CYAN)→ 同步 sdk 依赖$(C_RESET)\n"
	@cd "$(SDK_DIR)" && "$(UV)" sync
	@printf "$(C_CYAN)→ 可编辑安装 opensandbox 到 $(PYTHON)$(C_RESET)\n"
	@cd "$(SDK_DIR)" && { \
		"$(PYTHON)" -m pip install -e . -q 2>/dev/null \
		|| "$(PYTHON)" -m pip install -e . -q --user 2>/dev/null \
		|| "$(PYTHON)" -m pip install -e . -q --break-system-packages 2>/dev/null; \
	} \
	&& printf "$(C_GREEN)✓ opensandbox 可被 %s 导入$(C_RESET)\n" "$(PYTHON)" \
	|| printf "$(C_YELLOW)! 系统 python 安装失败, 可改用: %s -c 'import opensandbox'$(C_RESET)\n" "$(SDK_DIR)/.venv/bin/python"

# ---- 配置 ----
.PHONY: config
config: check-uv
	@if [ -f "$(SANDBOX_CONFIG)" ]; then \
		printf "$(C_YELLOW)配置已存在: $(SANDBOX_CONFIG) (如需重生成加 --force)$(C_RESET)\n"; \
	else \
		printf "$(C_CYAN)→ 生成 $(SANDBOX_CONFIG)$(C_RESET)\n"; \
		cd "$(SERVER_DIR)" && "$(UV)" run opensandbox-server init-config "$(SANDBOX_CONFIG)" --example docker; \
	fi

# ---- 卸载 ----
.PHONY: uninstall uninstall-full clean

uninstall:
	@printf "$(C_YELLOW)→ 移除软链$(C_RESET)\n"
	@rm -f "$(BINDIR)/$(SERVER_BIN)" $(foreach b,$(CLI_BINS),"$(BINDIR)/$(b)")
	@printf "$(C_YELLOW)→ 从系统 python 移除可编辑 opensandbox$(C_RESET)\n"
	@-$(PYTHON) -m pip uninstall -y opensandbox -q 2>/dev/null || true
	@printf "$(C_GREEN)✓ 软链 + 可编辑包已移除 (.venv 保留)$(C_RESET)\n"

uninstall-full: uninstall clean
	@printf "$(C_GREEN)✓ 软链 + 可编辑包 + .venv 全部清除$(C_RESET)\n"

clean:
	@printf "$(C_YELLOW)→ 删除 .venv$(C_RESET)\n"
	@rm -rf "$(SERVER_DIR)/.venv" "$(CLI_DIR)/.venv" "$(SDK_DIR)/.venv"
	@printf "$(C_GREEN)✓ .venv 已删除$(C_RESET)\n"

# ---- server 启停 ----
.PHONY: server server-bg server-stop

server: check-uv
	@printf "$(C_CYAN)→ 前台启动 server (Ctrl+C 停止)$(C_RESET)\n"
	@cd "$(SERVER_DIR)" && OPENSANDBOX_INSECURE_SERVER=YES "$(UV)" run opensandbox-server

server-bg: check-uv
	@printf "$(C_CYAN)→ 后台启动 server$(C_RESET)\n"
	@cd "$(SERVER_DIR)" && OPENSANDBOX_INSECURE_SERVER=YES \
		nohup "$(UV)" run opensandbox-server > "$(SERVER_LOG)" 2>&1 &
	@sleep 3
	@if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then \
		printf "$(C_GREEN)✓ server 已启动 (health=ok)，日志: $(SERVER_LOG)$(C_RESET)\n"; \
	else \
		printf "$(C_RED)✗ server 未就绪，查看日志: tail -50 $(SERVER_LOG)$(C_RESET)\n"; \
		tail -20 "$(SERVER_LOG)" 2>/dev/null || true; \
		exit 1; \
	fi

server-stop:
	@printf "$(C_YELLOW)→ 停止 server$(C_RESET)\n"
	@pkill -f "opensandbox_server.main" 2>/dev/null || true
	@printf "$(C_GREEN)✓ 已发送停止信号$(C_RESET)\n"

# ---- 验证 ----
.PHONY: check
check:
	@printf "$(C_CYAN)→ 验证安装$(C_RESET)\n"
	@fail=0; \
	for cmd in $(SERVER_BIN) $(CLI_BINS); do \
		if command -v $$cmd >/dev/null 2>&1; then \
			printf "  $(C_GREEN)✓ %s -> %s$(C_RESET)\n" "$$cmd" "$$(command -v $$cmd)"; \
		else \
			printf "  $(C_RED)✗ %s 未找到$(C_RESET)\n" "$$cmd"; \
			fail=1; \
		fi; \
	done; \
	if "$(PYTHON)" -c "import opensandbox" >/dev/null 2>&1; then \
		printf "  $(C_GREEN)✓ opensandbox 可被 %s 导入$(C_RESET)\n" "$(PYTHON)"; \
	else \
		printf "  $(C_YELLOW)⚠ %s 无法导入 opensandbox (可运行 make install-sdk)$(C_RESET)\n" "$(PYTHON)"; \
	fi; \
	exit $$fail

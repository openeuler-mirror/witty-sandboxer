# =============================================================================
# opencode-plugin — OpenSandbox agent infra plugin for OpenCode
#
# This Makefile installs / uninstalls the plugin into an OpenCode plugins
# directory. The plugin is pure-script (no build step): it consists of two
# files that simply need to be placed on the OpenCode plugin path.
#
#   agent-sandbox-infra.ts  — TypeScript plugin (registers 7 tools)
#   sandbox_runner.py      — Python CLI invoked by the plugin
#
# Install targets:
#   make install            # install into the project-local plugins dir
#                           # (./.opencode/plugins, overridable via DESTDIR)
#   make install-global     # install into the user-global plugins dir
#                           # (~/.config/opencode/plugins)
#   make uninstall          # remove from the project-local plugins dir
#   make uninstall-global   # remove from the user-global plugins dir
#
# Other targets:
#   make check              # verify the plugin files exist and python3 is present
#   make smoke              # run the bun smoke test (requires bun on PATH)
#   make clean              # remove project-local .opencode/plugins install
#   make help               # show this help
#
# Overridable variables:
#   DESTDIR          # prefix for project-local install (default: .)
#   PLUGIN_DIR       # project-local plugins dir (default: $(DESTDIR)/.opencode/plugins)
#   GLOBAL_PLUGIN_DIR # global plugins dir (default: $(HOME)/.config/opencode/plugins)
#   PYTHON           # python interpreter used for the check (default: python3)
# =============================================================================

DESTDIR          ?= .
PLUGIN_DIR       ?= $(DESTDIR)/.opencode/plugins
GLOBAL_PLUGIN_DIR ?= $(HOME)/.config/opencode/plugins
PYTHON           ?= python3
BUN              ?= bun

PLUGIN_FILES     := agent-sandbox-infra.ts sandbox_runner.py

# -----------------------------------------------------------------------------
# Install
# -----------------------------------------------------------------------------

.PHONY: install
install: check ## Install the plugin into the project-local plugins dir ($(PLUGIN_DIR))
	@mkdir -p "$(PLUGIN_DIR)"
	@for f in $(PLUGIN_FILES); do \
		cp -p "$$f" "$(PLUGIN_DIR)/$$f"; \
		echo "  installed $$f -> $(PLUGIN_DIR)/$$f"; \
	done
	@echo ""
	@echo "✅ Plugin installed to $(PLUGIN_DIR)"
	@echo "   Restart OpenCode for the 7 tools to become available."

.PHONY: install-global
install-global: check ## Install the plugin into the user-global plugins dir ($(GLOBAL_PLUGIN_DIR))
	@mkdir -p "$(GLOBAL_PLUGIN_DIR)"
	@for f in $(PLUGIN_FILES); do \
		cp -p "$$f" "$(GLOBAL_PLUGIN_DIR)/$$f"; \
		echo "  installed $$f -> $(GLOBAL_PLUGIN_DIR)/$$f"; \
	done
	@echo ""
	@echo "✅ Plugin installed to $(GLOBAL_PLUGIN_DIR)"
	@echo "   Restart OpenCode for the 7 tools to become available."

# -----------------------------------------------------------------------------
# Uninstall
# -----------------------------------------------------------------------------

.PHONY: uninstall
uninstall: ## Remove the plugin from the project-local plugins dir ($(PLUGIN_DIR))
	@for f in $(PLUGIN_FILES); do \
		rm -f "$(PLUGIN_DIR)/$$f"; \
		echo "  removed  $(PLUGIN_DIR)/$$f"; \
	done
	@if [ -d "$(PLUGIN_DIR)" ] && [ -z "$$(ls -A "$(PLUGIN_DIR)" 2>/dev/null)" ]; then \
		rmdir "$(PLUGIN_DIR)" 2>/dev/null || true; \
		echo "  removed empty dir $(PLUGIN_DIR)"; \
	fi
	@echo "✅ Plugin uninstalled from $(PLUGIN_DIR)"

.PHONY: uninstall-global
uninstall-global: ## Remove the plugin from the user-global plugins dir ($(GLOBAL_PLUGIN_DIR))
	@for f in $(PLUGIN_FILES); do \
		rm -f "$(GLOBAL_PLUGIN_DIR)/$$f"; \
		echo "  removed  $(GLOBAL_PLUGIN_DIR)/$$f"; \
	done
	@if [ -d "$(GLOBAL_PLUGIN_DIR)" ] && [ -z "$$(ls -A "$(GLOBAL_PLUGIN_DIR)" 2>/dev/null)" ]; then \
		rmdir "$(GLOBAL_PLUGIN_DIR)" 2>/dev/null || true; \
		echo "  removed empty dir $(GLOBAL_PLUGIN_DIR)"; \
	fi
	@echo "✅ Plugin uninstalled from $(GLOBAL_PLUGIN_DIR)"

# -----------------------------------------------------------------------------
# Checks / tests / clean
# -----------------------------------------------------------------------------

.PHONY: check
check: ## Verify plugin files exist and python3 is available
	@for f in $(PLUGIN_FILES); do \
		test -f "$$f" || { echo "missing plugin file: $$f" >&2; exit 1; }; \
	done
	@command -v "$(PYTHON)" >/dev/null 2>&1 || { echo "python3 not found on PATH" >&2; exit 1; }
	@echo "✅ plugin files present, $(PYTHON) available"

.PHONY: smoke
smoke: ## Run the bun smoke test (requires bun)
	@command -v "$(BUN)" >/dev/null 2>&1 || { echo "bun not found on PATH" >&2; exit 1; }
	$(BUN) run smoke_test.ts

.PHONY: clean
clean: ## Remove the project-local plugin install (./.opencode/plugins)
	@rm -rf "$(DESTDIR)/.opencode/plugins"
	@echo "✅ removed $(DESTDIR)/.opencode/plugins"

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

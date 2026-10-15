# =============================================================================
# process-sandbox — standalone Linux process sandbox (linux-sandbox binary)
#
# This Makefile makes the crate buildable/testable/packgable on its own, so the
# directory can be copied to another server and built standalone.
#
# Usage:
#   make build       # cargo build --release
#   make test         # cargo test (skips privileged bwrap_seccomp suite)
#   make fmt          # cargo fmt --all -- --check
#   make clippy       # cargo clippy --all-targets -- -D warnings
#   make package      # build a deployable tarball in dist/
#   make install      # install the binary to PREFIX/bin (default: /usr/local)
#   make uninstall
# =============================================================================

CARGO    ?= cargo
PREFIX   ?= /usr/local
BINDIR   ?= $(PREFIX)/bin
DIST_DIR ?= dist
BIN      := linux-sandbox

# Pinned toolchain is declared in rust-toolchain.toml; cargo auto-selects it.

.PHONY: build
build: ## Build the linux-sandbox binary (release)
	$(CARGO) build --release

.PHONY: fmt
fmt: ## Check formatting
	$(CARGO) fmt --all -- --check

.PHONY: clippy
clippy: ## Run clippy (warnings denied)
	$(CARGO) clippy --all-targets -- -D warnings

.PHONY: test
test: ## Run Rust unit + integration tests (skips privileged bwrap_seccomp suite)
	$(CARGO) test -- --skip bwrap_seccomp

.PHONY: check
check: fmt clippy test ## fmt + clippy + test

.PHONY: package
package: build ## Build a deployable tarball in $(DIST_DIR)
	@mkdir -p $(DIST_DIR)
	@ver=$$(grep -m1 '^version' Cargo.toml | sed 's/version = "\(.*\)"/\1/'); \
		stage="$(DIST_DIR)/process-sandbox-$$ver"; \
		rm -rf "$$stage"; mkdir -p "$$stage/bin"; \
		cp -p target/release/$(BIN) "$$stage/bin/"; \
		cp -p README.md README_zh.md LICENSE Cargo.toml Cargo.lock rust-toolchain.toml "$$stage/" 2>/dev/null || true; \
		tar -czf "$(DIST_DIR)/process-sandbox-$$ver.tar.gz" -C "$(DIST_DIR)" "process-sandbox-$$ver"; \
		rm -rf "$$stage"; \
		echo "📦 $(DIST_DIR)/process-sandbox-$$ver.tar.gz"

.PHONY: install
install: ## Install linux-sandbox to $(BINDIR) (requires a prior `make build`)
	@test -x target/release/$(BIN) || { echo "missing target/release/$(BIN); run 'make build' first" >&2; exit 1; }
	@mkdir -p $(DESTDIR)$(BINDIR)
	install -p -m 0755 target/release/$(BIN) $(DESTDIR)$(BINDIR)/

.PHONY: uninstall
uninstall: ## Remove linux-sandbox from $(BINDIR)
	rm -f $(DESTDIR)$(BINDIR)/$(BIN)

.PHONY: clean
clean: ## Remove build artifacts
	$(CARGO) clean
	rm -rf $(DIST_DIR)

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

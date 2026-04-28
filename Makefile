# ──────────────────────────────────────────────────────────────────────────────
#  adk-tools — developer Makefile
#
#  Targets
#  -------
#  install       Install the package + all extras in editable mode
#  install-dev   Install with full dev toolchain (ruff, mypy, pytest, …)
#  build         Build wheel + sdist into dist/
#  clean         Remove build artefacts, caches, and compiled files
#  test          Run the full test suite (pytest)
#  test-cov      Run tests with HTML coverage report
#  test-fast     Run tests, stop on first failure
#  verify        Lint (ruff), type-check (mypy), and run tests — full CI gate
#  lint          Run ruff linter
#  format        Auto-format with ruff
#  typecheck     Run mypy on the adk_tools package
#  run-agent     Launch the ADK web UI for the test_agent
#  run-agent-bg  Launch the ADK web UI in the background (logs to agent.log)
#  env           Copy test_agent/.env.example → test_agent/.env (if not present)
#  help          Print this help message
#
#  Quick start
#  -----------
#    make install-dev      # one-time setup
#    make env              # fill in test_agent/.env
#    make run-agent        # start the web UI
#    make verify           # full CI gate (lint + types + tests)
# ──────────────────────────────────────────────────────────────────────────────

# ── Config ─────────────────────────────────────────────────────────────────────
PYTHON      ?= python3
PIP         ?= $(PYTHON) -m pip
PACKAGE     := adk_tools
TEST_DIR    := tests
AGENT_DIR   := test_agent
TOOLS_DIR   := tools
ENV_FILE    := $(AGENT_DIR)/.env
ENV_EXAMPLE := $(AGENT_DIR)/.env.example
DIST_DIR    := dist
BUILD_DIR   := build
COV_DIR     := htmlcov

# Detect if .env exists for agent targets
HAS_ENV := $(shell test -f $(ENV_FILE) && echo yes || echo no)

# ── Colours (no-op if terminal doesn't support them) ───────────────────────────
BOLD  := \033[1m
RESET := \033[0m
GREEN := \033[32m
CYAN  := \033[36m
RED   := \033[31m

.DEFAULT_GOAL := help

# ── help ───────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  $(BOLD)adk-tools$(RESET) — developer Makefile"
	@echo ""
	@echo "  $(CYAN)Setup$(RESET)"
	@echo "    install        Install package + all extras (editable)"
	@echo "    install-dev    Install package + dev toolchain"
	@echo "    env            Copy .env.example → .env (skip if exists)"
	@echo ""
	@echo "  $(CYAN)Build$(RESET)"
	@echo "    build          Build wheel + sdist into dist/"
	@echo "    clean          Remove all build/test artefacts"
	@echo ""
	@echo "  $(CYAN)Test$(RESET)"
	@echo "    test           Run full test suite"
	@echo "    test-cov       Run tests with HTML coverage report"
	@echo "    test-fast      Run tests, stop on first failure (-x)"
	@echo ""
	@echo "  $(CYAN)Verify (CI gate)$(RESET)"
	@echo "    verify         lint + typecheck + test"
	@echo "    lint           Ruff linter"
	@echo "    format         Ruff auto-format"
	@echo "    typecheck      Mypy type-check"
	@echo ""
	@echo "  $(CYAN)Agent$(RESET)"
	@echo "    run-agent      Launch ADK web UI (foreground)"
	@echo "    run-agent-bg   Launch ADK web UI in background → agent.log"
	@echo ""


# ── Setup ──────────────────────────────────────────────────────────────────────
.PHONY: install
install:
	@echo "$(BOLD)→ Installing adk-tools [all] in editable mode$(RESET)"
	$(PIP) install -e ".[all]"

.PHONY: install-dev
install-dev:
	@echo "$(BOLD)→ Installing adk-tools [all,dev] in editable mode$(RESET)"
	$(PIP) install -e ".[all,dev]"
	@echo "$(GREEN)✓ Dev environment ready$(RESET)"

.PHONY: env
env:
	@if [ -f "$(ENV_FILE)" ]; then \
		echo "$(CYAN)ℹ  $(ENV_FILE) already exists — skipping copy$(RESET)"; \
	else \
		cp "$(ENV_EXAMPLE)" "$(ENV_FILE)"; \
		echo "$(GREEN)✓  Created $(ENV_FILE) from $(ENV_EXAMPLE)$(RESET)"; \
		echo "$(BOLD)   Edit $(ENV_FILE) and set GOOGLE_API_KEY before running the agent.$(RESET)"; \
	fi


# ── Build ──────────────────────────────────────────────────────────────────────
.PHONY: build
build: clean-dist
	@echo "$(BOLD)→ Building wheel + sdist$(RESET)"
	$(PYTHON) -m build
	@echo "$(GREEN)✓ Artefacts in $(DIST_DIR)/$(RESET)"
	@ls -lh $(DIST_DIR)/

.PHONY: clean-dist
clean-dist:
	rm -rf $(DIST_DIR) $(BUILD_DIR) $(PACKAGE).egg-info

.PHONY: clean
clean: clean-dist
	@echo "$(BOLD)→ Cleaning artefacts$(RESET)"
	find . -type d -name "__pycache__"  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache"  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache"  -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc"        -delete 2>/dev/null || true
	find . -type f -name "*.pyo"        -delete 2>/dev/null || true
	find . -type f -name ".coverage"    -delete 2>/dev/null || true
	rm -rf $(COV_DIR) agent.log
	@echo "$(GREEN)✓ Clean$(RESET)"


# ── Test ───────────────────────────────────────────────────────────────────────
.PHONY: test
test:
	@echo "$(BOLD)→ Running tests$(RESET)"
	$(PYTHON) -m pytest $(TEST_DIR) -v --tb=short

.PHONY: test-cov
test-cov:
	@echo "$(BOLD)→ Running tests with coverage$(RESET)"
	$(PYTHON) -m pytest $(TEST_DIR) \
		--cov=$(PACKAGE) \
		--cov-report=term-missing \
		--cov-report=html:$(COV_DIR) \
		-v --tb=short
	@echo "$(GREEN)✓ HTML coverage report: $(COV_DIR)/index.html$(RESET)"

.PHONY: test-fast
test-fast:
	@echo "$(BOLD)→ Running tests (stop on first failure)$(RESET)"
	$(PYTHON) -m pytest $(TEST_DIR) -x -v --tb=short


# ── Verify (CI gate) ───────────────────────────────────────────────────────────
.PHONY: verify
verify: lint typecheck test
	@echo ""
	@echo "$(GREEN)$(BOLD)✓ All checks passed$(RESET)"

.PHONY: lint
lint:
	@echo "$(BOLD)→ Ruff lint$(RESET)"
	$(PYTHON) -m ruff check $(PACKAGE) $(TEST_DIR)

.PHONY: format
format:
	@echo "$(BOLD)→ Ruff format$(RESET)"
	$(PYTHON) -m ruff format $(PACKAGE) $(TEST_DIR)
	$(PYTHON) -m ruff check --fix $(PACKAGE) $(TEST_DIR)

.PHONY: typecheck
typecheck:
	@echo "$(BOLD)→ Mypy type-check$(RESET)"
	$(PYTHON) -m mypy $(PACKAGE)


# ── Run agent ──────────────────────────────────────────────────────────────────
.PHONY: _check-env
_check-env:
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "$(RED)✗  $(ENV_FILE) not found.  Run:  make env$(RESET)"; \
		exit 1; \
	fi
	@if grep -q "your-gemini-api-key-here" "$(ENV_FILE)" 2>/dev/null; then \
		echo "$(RED)✗  GOOGLE_API_KEY is still the placeholder value.$(RESET)"; \
		echo "   Edit $(ENV_FILE) and set a real key from https://aistudio.google.com/apikey"; \
		exit 1; \
	fi

.PHONY: run-agent
run-agent: _check-env
	@echo "$(BOLD)→ Loading env from $(ENV_FILE) and launching ADK web UI$(RESET)"
	@echo "   Open http://127.0.0.1:8000 in your browser."
	@echo "   Press Ctrl-C to stop."
	@echo ""
	set -a && . $(ENV_FILE) && set +a && \
		ADK_TOOLS_DIR=$(TOOLS_DIR) adk web $(AGENT_DIR)

.PHONY: run-agent-bg
run-agent-bg: _check-env
	@echo "$(BOLD)→ Launching ADK web UI in the background$(RESET)"
	@echo "   Logs: agent.log"
	@echo "   Stop: make stop-agent"
	set -a && . $(ENV_FILE) && set +a && \
		ADK_TOOLS_DIR=$(TOOLS_DIR) adk web $(AGENT_DIR) > agent.log 2>&1 & \
		echo $$! > .agent.pid
	@echo "$(GREEN)✓ Agent started (PID $$(cat .agent.pid))  →  http://127.0.0.1:8000$(RESET)"

.PHONY: stop-agent
stop-agent:
	@if [ -f .agent.pid ]; then \
		PID=$$(cat .agent.pid); \
		kill $$PID 2>/dev/null && echo "$(GREEN)✓ Agent (PID $$PID) stopped$(RESET)" || echo "Process $$PID not running"; \
		rm -f .agent.pid; \
	else \
		echo "$(CYAN)ℹ  No .agent.pid found — nothing to stop$(RESET)"; \
	fi

.PHONY: agent-log
agent-log:
	@if [ -f agent.log ]; then tail -f agent.log; else echo "agent.log not found — run: make run-agent-bg"; fi

.PHONY: install test test-cov lint format typecheck check clean build demo demo-adk verify

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ --cov=agent_tools --cov-report=html --cov-report=term-missing

# ── Smoke-test the framework end-to-end via the sample agent ──────────────
# Exercises all four primary tool types (api, mcp, function, cta) and the
# dynamic-header paths. ``demo-adk`` additionally builds the google-adk
# LlmAgent over every registered tool (requires ``pip install google-adk``).
demo:
	python test_agent/demo.py

demo-adk:
	python test_agent/demo.py --adk

# Full validation — unit tests + runnable demo. Use this before pushing.
verify: test demo

lint:
	ruff check agent_tools tests
	ruff format --check agent_tools tests

format:
	ruff format agent_tools tests
	ruff check --fix agent_tools tests

typecheck:
	mypy agent_tools

check: lint typecheck test

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info"  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov"     -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true

build:
	python -m build

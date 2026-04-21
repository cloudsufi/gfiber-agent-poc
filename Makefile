.PHONY: install test lint typecheck check clean build

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ --cov=agent_tools --cov-report=html --cov-report=term-missing

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

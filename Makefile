.PHONY: help install test lint format check clean audit

help:
	@echo "Available targets:"
	@echo "  install  - Install dependencies with uv"
	@echo "  test     - Run tests with coverage"
	@echo "  lint     - Run ruff linting"
	@echo "  format   - Format code with ruff"
	@echo "  check    - Run all checks (lint, format, type, test)"
	@echo "  clean    - Remove generated files"
	@echo "  audit    - Run auditor on current repo"

install:
	uv sync
	uv pip install -e .

test:
	uv run -m pytest -v --cov=ghaw_auditor --cov-report=term-missing

lint:
	uvx ruff check .

format:
	uvx ruff format .

typecheck:
	uvx mypy .

check: lint format typecheck test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

audit:
	uv run ghaw-auditor scan --repo . --output .ghaw-auditor

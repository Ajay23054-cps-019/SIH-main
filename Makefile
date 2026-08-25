.PHONY: setup run test clean lint help

SHELL := /bin/bash
VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "✓ Setup complete. Activate with: source $(VENV)/bin/activate"

run: ## Start development server
	source $(VENV)/bin/activate && $(UVICORN) src.api.main:app --reload --host 0.0.0.0 --port 8000

run-bg: ## Start server in background
	source $(VENV)/bin/activate && $(UVICORN) src.api.main:app --host 0.0.0.0 --port 8000 &

test: ## Run tests
	source $(VENV)/bin/activate && $(PYTEST) tests/ -v --tb=short

test-cov: ## Run tests with coverage
	source $(VENV)/bin/activate && $(PYTEST) tests/ -v --cov=src --cov-report=html

clean: ## Clean generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/ .mypy_cache/ htmlcov/ .coverage
	rm -f *.db *.sqlite *.sqlite3

lint: ## Run linter
	source $(VENV)/bin/activate && python -m py_compile src/api/main.py

lint-all: ## Compile-check all Python files
	source $(VENV)/bin/activate && find src/ -name "*.py" -exec python -m py_compile {} +

freeze: ## Freeze current dependencies
	$(PIP) freeze > requirements.lock

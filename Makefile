.PHONY: setup test run clean lint

setup:
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
	@echo "Virtual environment ready. Run: . venv/bin/activate"

test:
	. venv/bin/activate && pytest tests/ -v

run:
	. venv/bin/activate && uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/

.PHONY: install test demo lint typecheck clean all

# Default: install and test
all: install test

install:
	uv sync

test:
	uv run pytest -v

demo:
	uv run python examples/worked_example.py

lint:
	uv run ruff check src/isnad tests examples
	uv run ruff format --check src/isnad tests examples

lint-fix:
	uv run ruff check --fix src/isnad tests examples
	uv run ruff format src/isnad tests examples

typecheck:
	uv run mypy src/isnad

check: lint typecheck test
	@echo "All checks passed."

coverage:
	uv run pytest --cov=isnad --cov-report=term-missing

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache *.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

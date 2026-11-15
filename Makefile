# Homebrew libs (pango etc.) for WeasyPrint on macOS: Apple Silicon and Intel
export DYLD_FALLBACK_LIBRARY_PATH := /opt/homebrew/lib:/usr/local/lib:$(DYLD_FALLBACK_LIBRARY_PATH)

.PHONY: setup hello-llm data extract warehouse quality copilot eval test lint format app all

setup:
	uv sync --all-extras
	uv run pre-commit install

hello-llm:
	uv run python scripts/hello_llm.py

data:
	uv run python -m p2p.data_gen.generate

extract:
	uv run python -m p2p.extraction.run

warehouse:
	cd warehouse && uv run dbt build --profiles-dir .

quality:
	uv run python -m p2p.quality_agent.run

copilot:
	uv run python -m p2p.copilot.run

eval:
	uv run python -m p2p.evals.run_all

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

app:
	uv run streamlit run src/p2p/app/main.py

all: data extract warehouse quality copilot eval

# Atalhos do projeto. Requer `uv` (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help
.PHONY: help setup fmt lint type test test-emulador cov check hooks run sim clean

help: ## Mostra os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Cria o venv (Python 3.12), instala dependências e os hooks de pre-commit
	uv sync --group dev
	uv run pre-commit install
	@test -f .env || cp .env.example .env
	@echo "Pronto. Edite o .env com valores locais (falsos)."

fmt: ## Formata o código
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Verifica lint e formatação (sem alterar arquivos)
	uv run ruff check .
	uv run ruff format --check .

type: ## Checagem de tipos
	uv run mypy

test: ## Roda os testes
	uv run pytest

test-emulador: ## Roda o teste de contrato do Repository também contra o emulador do Firestore (Docker)
	docker run -d --rm --name vocabot-firestore-emu -p 127.0.0.1:8686:8686 \
		gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators \
		gcloud emulators firestore start --host-port=0.0.0.0:8686
	@until curl -s http://127.0.0.1:8686 >/dev/null; do sleep 1; done
	FIRESTORE_EMULATOR_HOST=127.0.0.1:8686 uv run pytest tests/test_repository.py; \
		status=$$?; docker stop vocabot-firestore-emu >/dev/null; exit $$status

cov: ## Roda os testes com relatório de cobertura
	uv run pytest --cov --cov-report=term-missing

check: lint type test ## Tudo que a CI roda

hooks: ## Roda todos os hooks de pre-commit no repositório inteiro
	uv run pre-commit run --all-files

run: ## Sobe a API local (recarrega ao salvar)
	uv run uvicorn app.main:app --reload --port 8000

sim: ## Simulador de terminal (sem WhatsApp)
	uv run python -m sim

clean: ## Remove caches de ferramentas
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +

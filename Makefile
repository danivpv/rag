.PHONY: lambda-requirements docker-build lint type-check test seed synth deploy clean

lambda-requirements:
	uv export \
		--no-annotate --no-hashes \
		--format requirements-txt \
		--only-group lambda-requirements \
		--output-file src/rag/rag/runtime/requirements.txt \
		--locked

docker-build:
	docker build -t kb-agent-lambda -f src/rag/rag/runtime/Dockerfile .

lint:
	uv run ruff check --fix
	uv run ruff format

type-check:
	uv run ty check

test:
	uv run pytest

seed:
	uv run python scripts/seed.py

synth:
	uv run cdk synth

deploy:
	uv run cdk deploy --all

clean:
	rm -rf cdk.out src/rag/rag/runtime/requirements.txt
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +

# ── Profile ───────────────────────────────────────────────────────────────────
# Override on the CLI: make deploy AWS_PROFILE=production
AWS_PROFILE ?= default#oversight-test

# Export so all child processes (cdk, aws cli) inherit the profile
export AWS_PROFILE

.PHONY: lint type-check test seed synth deploy deploy-stateful \
		deploy-stateless clean lambda-requirements docker-build

# ── Quality ───────────────────────────────────────────────────────────────────

lint:
	uv run ruff check --fix
	uv run ruff format

type-check:
	uv run ty check

test:
	uv run pytest

# ── Data ingestion ────────────────────────────────────────────────────────────

seed:
	uv run seed

# ── CDK ───────────────────────────────────────────────────────────────────────
synth:
	uv run cdk synth

deploy-stateful: 
	uv run cdk deploy KBAgentStackStorage --profile $(AWS_PROFILE)

deploy-stateless: 
	uv run cdk deploy KBAgentStack --profile $(AWS_PROFILE)

deploy: seed
	uv run cdk deploy --all --profile $(AWS_PROFILE)

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	rm -rf cdk.out src/rag/rag/runtime/requirements.txt
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true


# ── Dev ───────────────────────────────────────────────────────────────────────
lambda-requirements:
	uv export \
		--no-annotate --no-hashes \
		--format requirements-txt \
		--only-group lambda-requirements \
		--output-file src/rag/rag/runtime/requirements.txt \
		--locked

docker-build:
	docker build -t kb-agent-lambda -f src/rag/rag/runtime/Dockerfile .

hello:
	uv run hello

hello-app:
	uv run hello-app --name $(NAME)

test-api:
	uv run python scripts/test_api.py

streamlit:
	uv run streamlit run client/app.py
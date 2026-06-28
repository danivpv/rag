# Metaprompting Strategy & AI Tools Usage

> [!NOTE]
> This document defines how AI coding assistants are used throughout the project, satisfying the brief's requirement: *"AI tools usage: include a short section on how you used coding assistants or LLMs while building the project."*

## 1. AI Tools in Use

| Tool | Purpose | When Used |
|------|---------|-----------| 
| **Antigravity (Claude / Gemini)** | Primary coding assistant | Architecture design, code generation, debugging, documentation |
| **Claude Haiku 4.5 (via Bedrock)** | LLM powering the KB Agent | Runtime — production inference for answer generation |

---

## 2. Global System Prompt

Use this as the foundational system prompt for **all** follow-up threads and coding sessions:

> "Act as an expert AWS Solutions Architect and ML Engineer. Your goal is to deliver a pragmatic, production-ready prototype that demonstrates strong architectural judgment, AWS best practices, and a clear understanding of RAG constraints.
> - **Architecture over Code Purity**: Prioritize clean CDK infrastructure, secure API design (Auth, least privilege IAM), and robust deployment patterns over textbook SOLID principles.
> - **Production Thinking**: Build for the immediate requirements (KISS/YAGNI) but explicitly design the architecture so the upgrade path to a fully hardened system (e.g., Fargate, Cognito, CI/CD) is clear and requires minimal refactoring.
> - **Core RAG Robustness**: Focus on the reliability of the core RAG pipeline (chunking strategy, vector retrieval, and prompt grounding) and uncertainty handling (confidence scoring, fallbacks) rather than advanced agentic extensions.
> - **Pragmatic Minimalism**: Keep the mental overhead low. Use descriptive naming and provide the simplest AWS-native architecture that solves the problem robustly within budget constraints.
> - **Anti-Hallucination & Context Fetching**: Do not hallucinate APIs or dependencies. Dynamically fetch context by reading the referenced markdown files in `docs/` before acting. Verify assumptions by consulting official AWS CDK documentation and Astral `uv` documentation. Ask clarifying questions if requirements are ambiguous.
> - **Stern Tooling & Environment Constraints**: ALWAYS use `uv` for Python dependency and environment management (`uv add`, `uv run python`, `uv venv`, `uv pip install`). NEVER use native `pip`, `venv`, or `python3`. ALWAYS beware of Git Bash escaping syntax on Windows; DO NOT pass complex inline JSON strings via bash arguments (like `--body '{"key": "val"}'`). Instead, strictly write payloads to physical files first in scripts folder and reference them (e.g., `fileb://scripts/payload.json`).
>
> **Implemented CDK Architecture (Phase 0 complete):**
> The CDK scaffolding is done and synthesizes successfully. Two stacks:
> - `KBAgentStackStorage` (termination_protection=True) — owns S3 bucket
> - `KBAgentStack` — owns Docker Lambda + API Gateway REST API
>
> Folder structure: `src/rag/api/infrastructure.py`, `src/rag/storage/infrastructure.py`, `src/rag/rag/infrastructure.py`, `src/rag/component.py`, `app.py`, `constants.py`
> All CDK infrastructure files are **complete and correct** — do NOT modify CDK files unless explicitly asked.
>
> **My current state of knowledge:**
> - AWS Architecture setup: [aws_architect_cheatsheet.md](file:///c:/Users/daniv/Programacion/danivpv/applications/aws_architect_cheatsheet.md)
> - AWS SSO setup: [aws_sso_cheatsheet.md](file:///c:/Users/daniv/Programacion/danivpv/applications/aws_sso_cheatsheet.md)
> - AWS CDK concepts and best practices (constructs, stacks, project structure, synthesis-time decisions): [aws_cdk_cheatsheet.md](file:///c:/Users/daniv/Programacion/danivpv/applications/aws_cdk_cheatsheet.md)
> - Reference prototype to scale: [Knowledge-Base-Agent-using-RAG](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG) (local clone of https://github.com/abhishek-RG/Knowledge-Base-Agent-using-RAG)"

---

## 3. Metaprompting Strategy Per Thread

Each thread gets a **focused context injection** that scopes the assistant's knowledge to what is strictly necessary. The key discipline is: **reference specific files**, not explanations of their content. The agent will read them.

> [!IMPORTANT]
> **Repo structure**: Implemented following the [AWS CDK recommended project structure](https://aws.amazon.com/es/blogs/developer/recommended-aws-cdk-project-structure-for-python-applications/). Each domain has its own folder with `infrastructure.py` (the Construct) and `runtime/` (the Lambda code). The top-level `app.py` assembles everything into two Stacks (stateful + stateless).

---

### Thread 1: CDK Infrastructure (Storage + API + App Wiring)

```
### System prompt: [GLOBAL SYSTEM PROMPT ABOVE]

### Role: AWS CDK Python developer

Read these files BEFORE writing any code:
- Architecture decisions and API contract: [02_Architecture_Comparison.md](file:///c:/Users/daniv/Programacion/oversight/docs/02_Architecture_Comparison.md)
- Implementation subsystems (§1 Project Structure, §5.1 Storage Stack, §5.4 API Stack, §5.5 CDK App): [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md)
- Existing pyproject.toml: [pyproject.toml](file:///c:/Users/daniv/Programacion/oversight/pyproject.toml)
- Existing cdk.json: [cdk.json](file:///c:/Users/daniv/Programacion/oversight/cdk.json)

### Key constraints:
- Use CONSTRUCT pattern (not separate Stacks per subsystem). One KBAgentStack, Constructs inside it.
- cdk.json already has "app": "python app.py" — update it to "uv run python app.py"
- Python CDK only, least-privilege IAM via grant_* methods, CfnOutput for all cross-stack references
- Do NOT hardcode resource names — let CDK generate them
- Verify constructs against official CDK v2 Python API docs before writing

### **Goal**: Write the CDK Constructs for S3 storage, API Gateway auth layer, and the top-level app + stack assembly. All files are currently empty stubs.

### **Deliverables**:
- [src/rag/storage/infrastructure.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/storage/infrastructure.py) — `StorageConstruct(Construct)` with S3 bucket, `RemovalPolicy.DESTROY`, `auto_delete_objects=True`, `CfnOutput` for bucket name
- [src/rag/api/infrastructure.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/api/infrastructure.py) — `ApiConstruct(Construct)` with API Gateway REST API, `/health` GET (no auth), `/query` POST (API key required), usage plan with throttling (10 rps/20 burst), `CfnOutput` for API URL and Key ID
- [src/rag/component.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/component.py) — `RagComponent(Construct)` that wires together `StorageConstruct`, `ComputeConstruct` (from Thread 2), and `ApiConstruct`. Exposes `bucket`, `fn`, `api` as properties.
- [app.py](file:///c:/Users/daniv/Programacion/oversight/app.py) — Root CDK App: one `KBAgentStack(Stack)` that instantiates `RagComponent`. Sets `env=cdk.Environment(region="us-east-1")`.
- `c:\Users\daniv\Programacion\oversight\constants.py` — Shared constants (region, stack name, memory size, timeout)
```

---

### Thread 2: Lambda RAG Engine (Docker + FastAPI + Bedrock)

```
### System prompt: [GLOBAL SYSTEM PROMPT ABOVE]

### Role: ML Engineer building a RAG pipeline on AWS Lambda

Read these files BEFORE writing any code:
- Full prototype analysis (what to keep vs replace): [01_Prototype_Analysis.md](file:///c:/Users/daniv/Programacion/oversight/docs/01_Prototype_Analysis.md)
- Docker Lambda decision, FAISS ETag cache pattern, Subsystem breakdown: [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md)
- Embedding model choice (§9) and streaming constraints (§8): [02_Architecture_Comparison.md](file:///c:/Users/daniv/Programacion/oversight/docs/02_Architecture_Comparison.md)
- Prototype retriever (port this, swap Google embeddings for Bedrock Titan): [retriever.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/rag/retriever.py)
- Prototype generator (port this, swap Gemini for Claude Haiku, lower temp): [generator.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/rag/generator.py)
- Prototype embedder (understand FAISS save/load pattern — we rewrite for S3/boto3): [embedder.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/rag/embedder.py)
- Prototype document loader (reuse loading logic in seed.py, not in Lambda): [document_loader.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/loaders/document_loader.py)

### Key constraints:
- Docker base image: `public.ecr.aws/lambda/python:3.12-x86_64` — do NOT change architecture or base image
- Bedrock embedding model: `amazon.titan-embed-text-v2:0`, `dimensions=512`, `normalize=True`
- Bedrock generation model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (read from env var BEDROCK_GENERATE_MODEL_ID)
- Temperature: 0.1 (NOT 0.7 like the prototype — grounded QA needs low temp to avoid hallucination)
- Use XML tags for Claude prompt: `<context>`, `<question>`, `<instructions>` — Claude's native format
- FAISS index loaded from S3 with ETag caching to /tmp — survives warm Lambda invocations, re-downloads only when index changes
- Lambda timeout 30s — budget one Bedrock embed call + one FAISS search + one Claude call; no N+1 Bedrock calls
- Structured JSON logs with request_id, latency_ms, model_id for CloudWatch
- DO NOT use LangChain in the Lambda runtime — use boto3 directly for Bedrock calls and raw faiss-cpu for vector ops

### Key porting decisions from the prototype:

**KEEP (port directly, swap provider):**
- Retrieval strategy: hybrid FAISS + keyword (retriever.py L131-206). Keep the `retrieve_with_scores` flow:
  1. Extract keywords via stop-word removal (L34-61)
  2. Expand query by appending keywords (L63-81)
  3. Over-retrieve: `min(k*3, 20)` candidates from FAISS
  4. Hybrid scoring: `combined_score = 0.7 * similarity_score + 0.3 * keyword_score` (L186)
  5. Sort descending by combined_score, take top-k
- Confidence scoring from generator.py (L256-305) — keep the exact heuristic formula:
  `confidence = 0.5*best_similarity + 0.3*avg_similarity + 0.1*consistency + 0.1*keyword_boost`
  then `confidence = confidence**0.9` and clamp to [0,1]
- Context formatting: `[Source: {source}, Chunk {chunk_idx}]\n{content}\n---\n` (retriever.py L208-228)
- Source metadata extraction from chunk metadata (retriever.py L230-260): filename, chunk_index, content_preview (first 300 chars)

**REPLACE (do not port as-is):**
- `GoogleGenerativeAIEmbeddings` → `boto3.client("bedrock-runtime").invoke_model()` with Titan Embed v2 body: `{"inputText": text, "dimensions": 512, "normalize": True}`
- `FAISS.from_documents()` / `save_local()` / `load_local()` (LangChain wrappers) → raw `faiss.IndexFlatIP` + `faiss.write_index()` + `faiss.read_index()` + `pickle` for chunk metadata
- `genai.GenerativeModel.generate_content()` → `boto3.client("bedrock-runtime").invoke_model()` with Claude message format
- `logging.basicConfig()` → `json.dumps()` structured log to stdout (Lambda → CloudWatch automatically)
- Gemini RAG prompt template → XML-tagged Claude prompt (see below)
- LangChain Document objects in Lambda → plain Python dicts/dataclasses (no LangChain in Lambda runtime)
- MongoDB query logging → structured CloudWatch JSON log line

**DISCARD (prototype-specific, no equivalent needed):**
- `nest_asyncio.apply()` — Streamlit async workaround, irrelevant in Lambda
- `_get_latest_model()` dynamic model detection — we pin the model via env var
- `explain_like_10` mode — out of scope for this submission
- `generate_related_questions()` — out of scope

### FAISS ETag cache pattern (critical for Lambda warm start performance):

```python
# At module level (survives warm invocations):
_index: faiss.IndexFlatIP | None = None
_chunks: list[dict] | None = None        # chunk dicts with text + metadata
_cached_etag: str | None = None

def _load_or_refresh(s3_client, bucket: str) -> None:
    global _index, _chunks, _cached_etag
    head = s3_client.head_object(Bucket=bucket, Key="index/index.faiss")
    etag = head["ETag"]
    if etag == _cached_etag and _index is not None:
        return  # warm hit — index unchanged, skip download
    s3_client.download_file(bucket, "index/index.faiss", "/tmp/index.faiss")
    s3_client.download_file(bucket, "index/index.pkl",   "/tmp/index.pkl")
    _index = faiss.read_index("/tmp/index.faiss")
    with open("/tmp/index.pkl", "rb") as f:
        _chunks = pickle.load(f)
    _cached_etag = etag
```

### Claude Haiku prompt structure (XML tags, not Gemini plain-text format):

```python
SYSTEM_PROMPT = """You are a knowledge base assistant. Answer questions strictly from the provided context.
If the answer is not in the context, say: 'I don't have information about this in the knowledge base.'
Be concise and factual."""

USER_PROMPT = """<context>
{context}
</context>

<question>
{question}
</question>

<instructions>
- Answer only from the context above. Do not use external knowledge.
- Be concise and direct.
- Cite the source document for each key claim.
</instructions>"""
```

Bedrock invoke body (Claude Messages API):
```json
{
  "anthropic_version": "bedrock-2023-05-31",
  "max_tokens": 1000,
  "temperature": 0.1,
  "system": "<SYSTEM_PROMPT>",
  "messages": [{"role": "user", "content": "<USER_PROMPT with context+question>"}]
}
```

### API response contract (exact fields required):

```json
{
  "answer": "string",
  "confidence": 0.84,
  "sources": [
    {"document_id": "rag_optimization.pdf", "chunk_id": "rag_optimization#4",
     "score": 0.91, "excerpt": "first 300 chars of chunk..."}
  ],
  "metadata": {
    "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "retrieval_strategy": "faiss_hybrid_512d",
    "request_id": "uuid",
    "latency_ms": 1240
  }
}
```

### FastAPI + Mangum wiring:

```python
# main.py
from fastapi import FastAPI
from mangum import Mangum
from api.routes import router

app = FastAPI(title="KB Agent API", version="1.0.0")
app.include_router(router)
# /docs endpoint is available automatically — Mangum forwards all paths
handler = Mangum(app, lifespan="off")
```

### Environment variables (read via os.environ, NOT pydantic-settings in Lambda):
- `S3_BUCKET_NAME` — bucket containing index/index.faiss and index/index.pkl
- `BEDROCK_REGION` — AWS region for Bedrock client (NOT AWS_REGION which is Lambda-reserved)
- `BEDROCK_EMBED_MODEL_ID` — `amazon.titan-embed-text-v2:0`
- `BEDROCK_GENERATE_MODEL_ID` — `us.anthropic.claude-haiku-4-5-20251001-v1:0`

### **Goal**: Build the full RAG pipeline inside the Docker Lambda. Port from Google Gemini to Amazon Bedrock. All service files under `src/rag/rag/runtime/` are empty stubs.

### **Deliverables**:
- [src/rag/rag/runtime/Dockerfile](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/Dockerfile) — `public.ecr.aws/lambda/python:3.12-x86_64` base image
- [src/rag/rag/runtime/requirements.txt](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/requirements.txt) — `boto3, mangum, fastapi, faiss-cpu, numpy, pypdf, python-docx, pydantic` (no LangChain, no google libs)
- [src/rag/rag/runtime/main.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/main.py) — FastAPI app + Mangum handler
- [src/rag/rag/runtime/api/routes.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/api/routes.py) — `/health` GET and `/query` POST endpoints
- [src/rag/rag/runtime/api/models.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/api/models.py) — Pydantic `QueryRequest` and `QueryResponse` matching the contract above
- [src/rag/rag/runtime/services/embedder.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/services/embedder.py) — boto3 Bedrock Titan Embed v2 + ETag-cached FAISS load from S3
- [src/rag/rag/runtime/services/retriever.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/services/retriever.py) — port of prototype hybrid FAISS+keyword retrieval, using raw faiss-cpu
- [src/rag/rag/runtime/services/generator.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/services/generator.py) — boto3 Claude Haiku, XML-tagged prompt, port of confidence scoring
- [src/rag/rag/runtime/services/logger.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/services/logger.py) — structured JSON stdout logger (no basicConfig)
- [src/rag/rag/runtime/config.py](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/config.py) — pydantic-settings singleton
```

---

### Thread 2.5: Build Setup & Dependency Management

```
### System prompt: [GLOBAL SYSTEM PROMPT ABOVE]

### Role: Python tooling and build specialist

Read these files BEFORE writing any code:
- Existing pyproject.toml: [pyproject.toml](file:///c:/Users/daniv/Programacion/oversight/pyproject.toml)
- [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md) (Section 4: Docker Lambda requirements)

### Key constraints:
- Use `uv` strictly for all package management. No pip commands in scripts.
- The Lambda container will use a native multi-stage build directly from `uv.lock`, abandoning `requirements.txt`.
- Add convenient run scripts to the `Makefile` (e.g., `lambda-requirements`, `docker-build`, `lint`, `test`, `seed`).

### **Goal**: Configure a robust `uv` build backend, set up dependency groups, and create a multi-stage Dockerfile relying on BuildKit cache overlays and `uv.lock`.

### **Deliverables**:
- Updated `pyproject.toml` and `Makefile`
- `dockerfile_cheatsheet.md` capturing Docker architecture learnings.
- [src/rag/rag/runtime/Dockerfile](file:///c:/Users/daniv/Programacion/oversight/src/rag/rag/runtime/Dockerfile) using ephemeral multi-stage architecture, native `--mount=type=cache`, non-destructive bind mounts (`--mount=type=bind`), and decoupled project extraction (`uv sync --no-install-project`).
```

---

### Thread 3: Deployment, Seeding & Smoke Tests

```
### System prompt: [GLOBAL SYSTEM PROMPT ABOVE]

### Role: DevOps engineer writing deployment scripts
Read before building:
- Chunking and embedding strategy: [01_Prototype_Analysis.md](file:///c:/Users/daniv/Programacion/oversight/docs/01_Prototype_Analysis.md) (§2.1, §2.3)
- AWS SSO Context: [aws_sso_cheatsheet.md](file:///c:/Users/daniv/Programacion/danivpv/applications/aws_sso_cheatsheet.md)
- Prototype document loader: [document_loader.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/loaders/document_loader.py)

### Key constraints for Deployment:
- I lack permissions to deploy on the candidate account. Instead, we will deploy to my personal AWS Organization.
- You must guide me step-by-step through creating a new Member Account explicitly named `oversight-test` via `aws organizations create-account` and granting my SSO user `AdministratorAccess`.
- Provide the CLI commands to log in via SSO (`aws sso login`) and bootstrap the CDK in this new account.

### Key constraints for Seeding & Tests:
- seed.py must use boto3 directly (not CDK) — it runs AFTER cdk deploy
- Reads bucket name from .env (S3_BUCKET_NAME) or falls back to CloudFormation describe-stacks
- Embedding: Bedrock Titan v2, dimensions=512, normalize=True — must match Lambda embedder exactly
- FAISS: use raw `faiss.IndexFlatIP` + `faiss.write_index()`
- test_api.py: writes all request payloads to scripts/payloads/ directory FIRST
- test_api.py: reads API_BASE_URL and API_TOKEN from .env

### **Goal**: Local scripts to populate S3/FAISS, step-by-step AWS SSO member account deployment, and validate the deployed API end-to-end.

### **Deliverables**:
- Step-by-step deployment guide for SSO Member account creation and CDK bootstrap
- [scripts/seed.py](file:///c:/Users/daniv/Programacion/oversight/scripts/seed.py) — Loads docs, embeds via Bedrock, saves FAISS index to S3
- [scripts/test_api.py](file:///c:/Users/daniv/Programacion/oversight/scripts/test_api.py) — End-to-end smoke tests against live API
```

---

### Thread 4: Streamlit Client

```
### System prompt: [GLOBAL SYSTEM PROMPT ABOVE]

### Role: Frontend developer building a thin API client
Read the API contract (§7) before building: [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md)

### Key constraints:
- ~100 lines total — NO business logic, NO RAG code, just HTTP calls
- Reads API_BASE_URL and API_TOKEN from .env using python-dotenv
- Sends POST /query with `{"question": str, "top_k": 5}` JSON body, header `x-api-key: <token>`
- Displays: answer (st.markdown), confidence (st.progress), sources (st.expander), metadata (st.caption)
- Handles errors gracefully: 403 (bad token), 500 (server error), connection timeout
- GET /health before first query to confirm the API is reachable; show a warning banner if not

### **Goal**: A thin (~100 line) local Streamlit app that reads credentials from `.env` and calls the AWS API.

### **Deliverables**:
- [client/app.py](file:///c:/Users/daniv/Programacion/oversight/client/app.py) — Streamlit UI showing question, answer, confidence, sources, metadata
- `.env.example` — Template with `API_BASE_URL` and `API_TOKEN` placeholders
```

---

### Thread 5: Debug

```
### System prompt: [GLOBAL SYSTEM PROMPT ABOVE]

### Role: DevOps/debugging specialist
Context: [PASTE error message + stack trace + relevant file excerpt]

### Key constraints:
- Minimal targeted changes — do not refactor working code
- Explain the root cause before proposing the fix
- For CDK errors: run `uv run cdk synth` first to isolate synthesis vs deployment errors
- For Lambda errors: check CloudWatch logs at /aws/lambda/<function-name>
- For FAISS dimension mismatch: confirm both seed.py and embedder.py use dimensions=512
- For Bedrock access errors: check model access in us-east-1 console AND that IAM policy includes both foundation-model and inference-profile ARNs
```

---

## 4. Context Files Reference Map

| Thread | Must Read Before Acting |
|--------|------------------------|
| CDK Infrastructure ✅ | Complete — see existing files |
| Lambda RAG Engine | [01_Prototype_Analysis.md](file:///c:/Users/daniv/Programacion/oversight/docs/01_Prototype_Analysis.md), [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md), [02_Architecture_Comparison.md](file:///c:/Users/daniv/Programacion/oversight/docs/02_Architecture_Comparison.md) §9, prototype [retriever.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/rag/retriever.py), [generator.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/rag/generator.py), [embedder.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/rag/embedder.py) |
| Streamlit Client | [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md) §7 (API contract) |
| Seeding & Tests | [01_Prototype_Analysis.md](file:///c:/Users/daniv/Programacion/oversight/docs/01_Prototype_Analysis.md) §2.1 §2.3, [03_Implementation_Guide.md](file:///c:/Users/daniv/Programacion/oversight/docs/03_Implementation_Guide.md), prototype [document_loader.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/loaders/document_loader.py), [text_splitter.py](file:///c:/Users/daniv/Programacion/Knowledge-Base-Agent-using-RAG/utils/text_splitter.py) |

---

## 5. How AI Assistants Were Used (README Section Draft)

```markdown
### AI Tools Usage

This project was built with the assistance of AI coding tools:

**Planning & Architecture**: Used Antigravity (AI coding assistant) to:
- Analyze the reference prototype's RAG pipeline, retrieval strategy, and confidence scoring
- Compare architecture alternatives (Lambda vs Fargate vs Bedrock KB vs AgentCore)
  across AWS Well-Architected Framework pillars and the $20 budget constraint
- Design the CDK construct/stack structure and API contract
- Identify cost risks (e.g., AOSS pricing blowing the budget)

**Implementation**: Used Antigravity to generate first drafts of:
- CDK Construct files (StorageConstruct, ComputeConstruct, ApiConstruct, RagComponent)
- Lambda RAG pipeline ported from Google Gemini to Amazon Bedrock (Titan Embed + Claude Haiku)
- Streamlit client, seeding script, and API smoke tests

**Documentation**: Used AI to draft architecture documentation and Mermaid diagrams.

**Verification**: All AI-generated code was reviewed for correctness against AWS documentation,
tested locally, and validated against the API contract before submission.

**What was NOT AI-generated**:
- Architecture decisions and tradeoff judgments
- CDK best practice choices (construct-per-folder structure, synthesis-time decisions)
- Final README narrative and production improvement analysis
```

---

## 6. Prompting Best Practices

### For Bedrock Claude Haiku (Production RAG Prompt)

| Technique | Applied? | Notes |
|-----------|:--------:|-------|
| **System prompt** | ✅ | Grounding constraints + role |
| **XML tags** | ✅ | `<context>`, `<question>`, `<instructions>` — Claude's preferred format |
| **Temperature** | ✅ | 0.1 (prototype uses 0.7 — too high for grounded QA) |
| **Max tokens** | ✅ | 1000 for answer |
| **Few-shot examples** | ❌ | Not needed for simple QA, saves tokens |
| **Chain-of-Thought** | ❌ | Increases latency and cost — overkill here |
| **Prompt caching** | ❌ | Variable context windows make this unreliable |

### For AI Coding Assistant (Development Threads)

| Technique | When | Example |
|-----------|------|---------|
| **File reference anchoring** | Every thread start | Reference exact file paths, not paraphrased content |
| **Read-before-act instruction** | Always | "Read `docs/03_Implementation_Guide.md §5.2` BEFORE writing code" |
| **Constraint emphasis** | Budget/time-sensitive | "Must stay under $20 total AWS spend" |
| **Porting with diff** | Code migration | "Port this exact function, keeping the same algorithm, swapping `GoogleGenerativeAI` for `boto3` Bedrock" |
| **Verification requests** | After generation | "Validate this against the official CDK v2 Python API docs" |

---

## 7. Transparency Guidelines

Per the brief: *"You may use AI coding assistants such as Copilot, Cursor, ChatGPT, Claude, or similar tools."*

1. **Be honest**: Don't hide AI usage. The brief explicitly permits and encourages it
2. **Show judgment**: AI generates code; the architect makes decisions. Highlight WHERE AI suggestions were overridden
3. **Document process**: The AI tools section should show AI was used as a force multiplier, not a replacement for engineering judgment
4. **Quality matters**: AI-generated code that's buggy reflects poorly. Review everything
5. **Architecture is yours**: The most valued rubric items (architecture judgment, production thinking, communication) require human insight that AI amplifies but doesn't replace

# Blockers Resolution Guide (Do Today — Thursday)

> [!CAUTION]
> These are **blocking prerequisites** for Friday implementation. Each one takes 5-30 minutes. Resolve all today before stopping.

## Blocker 1: AWS Credentials for CLI/CDK (UNBLOCKED!)

### The Situation
You have a mixed environment: your personal profiles (`default`, `workshop`) use AWS IAM Identity Center (SSO), while the oversight account requires traditional Access Keys. 
**Yes, it is 100% compatible to mix SSO and Access Keys!** The AWS CLI isolates them perfectly using the `--profile` flag.

### Resolution Steps

**Step 1** — Configure a dedicated profile for the oversight using the keys from `candidates-10_accessKeys.csv`. Run this in your terminal:
```bash
aws configure --profile oversight
# AWS Access Key ID [None]: [REDACTED]
# AWS Secret Access Key [None]: [REDACTED]
# Default region name [None]: us-east-1
# Default output format [None]: json
```

**Step 2** — Validate the profile works:
```bash
# Test basic access (should return your candidates-10 ARN)
aws sts get-caller-identity --profile oversight

# Test Bedrock access (critical)
aws bedrock list-foundation-models --region us-east-1 --query "modelSummaries[?modelId=='us.anthropic.claude-haiku-4-5-20251001-v1:0'].modelId" --profile oversight

# Test S3 access
aws s3 ls --profile oversight
```

**Step 3** — Tell AWS CDK to use this profile. 
When working with CDK, you must explicitly pass the profile flag, OR set the environment variable so you don't have to type it every time:
```bash
# Option A: Pass it to every CDK command
cdk synth --profile oversight
cdk deploy --profile oversight

# Option B: Set it for your current terminal session (Recommended!)
export AWS_PROFILE=oversight
cdk synth
```

**Step 4** — Verify IAM Permissions on the oversight:
```bash
# Check what policies Mostafa gave you
aws iam list-attached-user-policies --user-name candidates-10 --profile oversight
```
> [!TIP]
> If you see `AdministratorAccess`, `PowerUserAccess`, or a custom policy with the required wildcard permissions, you are fully unblocked to deploy the CDK stack!

---

## Blocker 2: Enable Bedrock Foundation Models

Bedrock models must be **explicitly enabled** in the AWS Console before you can invoke them. This is a one-time console action.

> [!WARNING]
> **Why this can't be automated via CDK/CLI:**
> Enabling foundation models in Bedrock requires accepting the End User License Agreements (EULAs) from providers like Anthropic. AWS intentionally does not expose an API or CDK construct to automatically "click agree" on these legal agreements. It must be done manually by a human in the console for every new AWS account.

### Models to Enable

| Model | Model ID | Why |
|-------|---------|-----|
| **Titan Embeddings v2** | `amazon.titan-embed-text-v2:0` | Embedding generation |
| **Claude 3.5 Haiku** | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Answer generation |

### How to Enable (5 min)

1. Go to **AWS Console → Amazon Bedrock → Model Garden** (left sidebar)
2. Fill Anthropic usage form

### Validate After Enabling

```bash
# Test Titan Embeddings
aws bedrock-runtime invoke-model \
  --model-id "amazon.titan-embed-text-v2:0" \
  --body '{"inputText":"hello world","dimensions":512,"normalize":true}' \
  --region us-east-1 \
  /tmp/embed_test.json && cat /tmp/embed_test.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Embedding dim: {len(d[\"embedding\"])}')"
# Expected: "Embedding dim: 512"

# Test Claude 4.5 Haiku
aws bedrock-runtime invoke-model \
  --model-id "us.anthropic.claude-haiku-4-5-20251001-v1:0" \
  --body file:///tmp/claude_test_body.json \
  --region us-east-1 \
  /tmp/claude_test.json
# Expected: "Hi" or similar
```

---

## Blocker 3: CDK Bootstrap

CDK requires a one-time **bootstrap** step per account+region. This creates an S3 bucket and IAM roles that CDK uses to store assets and deploy stacks.

```bash
# Install CDK CLI (if not installed)
bun install -g aws-cdk

# Verify version
cdk --version  # Should be 2.x

# Bootstrap (one-time per account/region)
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# Get your account ID:
aws sts get-caller-identity --query Account --output text
# Then: cdk bootstrap aws://123456789012/us-east-1
```

This creates a stack called `CDKToolkit`. Verify:
```bash
aws cloudformation describe-stacks --stack-name CDKToolkit --query "Stacks[0].StackStatus"
# Expected: "CREATE_COMPLETE" or "UPDATE_COMPLETE"
```

> [!NOTE]
> CDK bootstrap needs `cloudformation:CreateStack`, `s3:CreateBucket`, and `iam:CreateRole`. If it fails, contact admin.

---

## Blocker 4: Lambda Package Size (faiss-cpu) (done, decided on docker deployment)

`faiss-cpu` is a C-extension that's ~60-80MB compiled. With other ML deps (langchain, numpy, etc.) you can exceed Lambda's **50MB zip / 250MB unzipped** limit.

### Check Before Building

```bash
# Create a test virtualenv and check faiss-cpu size
uv venv /tmp/test-venv
source /tmp/test-venv/bin/activate
pip install faiss-cpu numpy boto3 langchain langchain-community pypdf python-docx

du -sh /tmp/test-venv/lib/python3.*/site-packages/ 
# If > 250MB → use Docker-based Lambda (ECR image, 10GB limit)
# If < 250MB → use zip-based Lambda Layer
```

### Mitigation Plan

**Option A — Lambda Layer (preferred if <250MB)**:
- Build layer on Amazon Linux 2023 (same OS as Lambda runtime)
- CDK `lambda.LayerVersion` with custom build script

**Option B — Docker Lambda (fallback)**:
```dockerfile
FROM public.ecr.aws/lambda/python:3.12
COPY requirements.txt .
RUN pip install -r requirements.txt -t /var/task
COPY lambda_handler/ /var/task/
CMD ["main.handler"]
```

CDK with Docker Lambda:
```python
from aws_cdk import aws_lambda as lambda_
from aws_cdk.aws_ecr_assets import DockerImageAsset

handler = lambda_.DockerImageFunction(
    self, "KBAgentHandler",
    code=lambda_.DockerImageCode.from_image_asset("./lambda_handler"),
    memory_size=1024,
    timeout=Duration.seconds(30),
)
```

> [!TIP]
> **Decide upfront which option.** Docker Lambda is safer (no size limit) but requires Docker running. Lambda Layer requires building on Linux (use WSL or a lightweight Docker build step). **My recommendation: go straight to Docker Lambda** — it's more production-realistic, eliminates the size gamble, and reviewers will appreciate the ECR/container story.

---

## Blocker 5: Project Scaffolding (Done)

Initialize the new repo with the correct structure. Validated pattern from `oversight` project:

```bash
# In your projects directory
cd c:\Users\daniv\Programacion

# Initialize the project
mkdir aws-kb-agent
cd aws-kb-agent
git init

# Use --package mode (src/ layout + [project.scripts] + build-system)
uv init --package aws-kb-agent

# This creates:
# src/aws_kb_agent/__init__.py
# pyproject.toml  (with [build-system] hatchling)
# README.md
# uv.lock  (empty for now)

# Verify the entry point pattern works
# Add to pyproject.toml under [project.scripts]:
# kb-agent = "aws_kb_agent:main"
# Add main() to src/aws_kb_agent/__init__.py
uv run kb-agent  # Should print hello
```

**Add project dependencies today** (before you need them):
```bash
# CDK
uv add "aws-cdk-lib>=2.150.0" constructs

# Lambda + AWS
uv add boto3 mangum fastapi

# RAG
uv add faiss-cpu langchain langchain-community pypdf python-docx

# Config
uv add pydantic-settings python-dotenv

# Dev tools
uv add --dev pytest pytest-asyncio ruff
```

**Create directory structure** (manually or with a script):
```bash
mkdir -p src/aws_kb_agent
mkdir -p lambda_handler/{api,rag,utils}
mkdir -p infra
mkdir -p sample-docs
mkdir -p scripts
mkdir -p client

# Touch __init__ files
touch lambda_handler/__init__.py
touch lambda_handler/api/__init__.py
touch lambda_handler/rag/__init__.py
touch lambda_handler/utils/__init__.py
touch infra/__init__.py
```

**Add CDK entry points**:
```toml
# In pyproject.toml, add:
[project.scripts]
kb-agent = "aws_kb_agent:main"
cdk-app = "aws_kb_agent.infra.app:main"   # CDK app entrypoint
```

> [!NOTE]
> `uv run cdk synth` won't work out of the box because CDK CLI is a Node.js tool. You still run `cdk synth` directly (after `npm install -g aws-cdk`). For the app itself use `uv run python app.py` or configure `cdk.json` to point to your venv Python.

**Configure `cdk.json`**:
```json
{
  "app": "uv run python app.py",
  "watch": {
    "include": ["**"],
    "exclude": ["README.md", "cdk*.json", ".git/**", ".venv/**"]
  }
}
```

This makes `cdk synth` automatically use `uv run python app.py` — no venv activation needed.

---

## Blocker 6: Write-Through FAISS Pattern — Rubric Alignment (Done, left as an unlikely extension)

### Your Proposed Pattern (head_object ETag versioning)

```python
FAISS_INDEX = None
CURRENT_ETAG = None

def load_or_update_index():
    global FAISS_INDEX, CURRENT_ETAG
    metadata = s3.head_object(Bucket=BUCKET_NAME, Key=INDEX_KEY)
    latest_etag = metadata['ETag']
    if latest_etag == CURRENT_ETAG:
        return  # Warm hit, use cached index
    s3.download_file(BUCKET_NAME, INDEX_KEY, LOCAL_PATH)
    FAISS_INDEX = faiss.read_index(LOCAL_PATH)
    CURRENT_ETAG = latest_etag
```

### Analysis

**This is a great pattern.** Let me break down what it demonstrates:

| Property | Status | Notes |
|----------|:------:|-------|
| **Correctness** | ✅ | ETag changes on every PUT, reliable version check |
| **Cost efficiency** | ✅ | `head_object` costs ~$0.0004/1000 calls (negligible) |
| **Separation of concerns** | ✅ | "Read Lambda" vs future "Write Lambda" are decoupled |
| **Lambda warm cache exploitation** | ✅ | Global scope survives across warm invocations |
| **No race condition** | ✅ | Lambda is single-threaded per instance — atomic check |
| **Works with versioning** | ⚠️ | ETags are only reliable with S3 versioning disabled OR using VersionId |

**One caveat**: S3 ETags for multipart uploads are hashes of hashes, not the file hash. For small FAISS indexes (<100MB) there are no multipart uploads so the ETag == MD5. Fine for our case.

### Rubric Alignment

| Rubric Item | Impact | Assessment |
|-------------|:------:|-----------|
| Architecture judgment | High | Shows you understand Lambda execution model + S3 optimizations |
| Production thinking | High | Explicitly addresses cold start vs warm start behavior |
| API design | Neutral | This is internal Lambda logic |
| Code quality | High | Clean pattern, well-commented |
| Explainability | High | Easy to explain in a README or interview |

**Verdict: YES, implement it.** Not for document upload (that's out of scope), but for the **read path**. The ETag check costs microseconds and demonstrates production-level thinking about Lambda execution models.

**Where to use it**: In the Lambda `/query` handler's startup logic.

### Where NOT to Use It (Yet)

The "Write Lambda" (re-seeding the index on document upload) **is out of scope** for the submission but perfectly documented as a future extension:

```
Future: Upload endpoint → Write Lambda triggers:
  1. Receive new doc from S3 event
  2. Chunk + embed new document
  3. Merge into existing FAISS index
  4. Upload new index to S3 (new ETag)
  5. All running Read Lambda instances detect new ETag → auto-refresh
```

This is exactly the kind of production design thinking the rubric rewards, even if not implemented.

---

## Today's Checklist Summary

```
CREDENTIALS
[ ] aws sts get-caller-identity → returns account ID
[ ] aws bedrock list-foundation-models → returns model list
[ ] Note your AWS account ID for CDK bootstrap

BEDROCK
[ ] Enable Amazon Titan Text Embeddings V2 in Bedrock console
[ ] Enable Anthropic Claude 3 Haiku in Bedrock console
[ ] Validate both with CLI test commands above

CDK
[ ] npm install -g aws-cdk
[ ] cdk bootstrap aws://ACCOUNT_ID/us-east-1

PACKAGE SIZE
[ ] Check faiss-cpu + deps size
[ ] Decision: Lambda Layer or Docker Lambda

SCAFFOLDING
[ ] mkdir aws-kb-agent && cd aws-kb-agent && git init
[ ] uv init --package aws-kb-agent
[ ] uv add [dependencies listed above]
[ ] Create directory structure
[ ] Create cdk.json with "app": "uv run python app.py"
[ ] Verify: uv run python app.py (CDK entrypoint works)
[ ] git add . && git commit -m "chore: initial project scaffolding"
```

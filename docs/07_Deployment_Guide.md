# Deployment Guide — KB Agent (oversight-test Account)





---

## Prerequisites Checklist

- [x] AWS CLI v2 installed (`aws --version`)
- [x] `uv` installed and in PATH
- [x] Docker Desktop running (needed for CDK Docker Lambda image build)
- [x] Logged into management account SSO: `aws sso login` (default profile)
- [x] Management account has AWS Organizations enabled

---

## Phase 1 — Create the Member Account (Console)

> [!CAUTION]
> Creating a real AWS account linked to your organization cannot be trivially undone (account closure takes 90 days). 

1. Log into your management account AWS Console.
2. Go to **AWS Organizations**.
3. Click **Add an AWS account**.
4. Enter account name (e.g. `oversight-test`) and your email address (e.g. `danivpv+oversight-test@outlook.com`).
5. Click **Create AWS account**.
6. Wait for creation to finish, then note the **12-digit Account ID**.

---

## Phase 2 — Grant SSO Access

### Step 2.1 — Grant AdministratorAccess on the new account (Console)

1. In your management account AWS Console, go to **IAM Identity Center**.
2. On the left sidebar under "Multi-account permissions", click **AWS accounts**.
3. Check the box next to your new `oversight-test` account and click **Assign users or groups**.
4. Go to the **Users** tab, select your user, and click **Next**.
5. Select the **AdministratorAccess** permission set and click **Submit**.

---

## Phase 3 — Configure the CLI Profile

### Step 3.1 — Add oversight-test profile interactively

Run the interactive AWS CLI configuration tool:

```bash
aws configure sso
```

When prompted, fill in the following:
- **SSO session name**: `oversight-test`
- **SSO start URL**: (Your SSO start URL, e.g. `https://d-xxxx.awsapps.com/start`)
- **SSO region**: `us-east-1`
- **SSO registration scopes**: (Press Enter for default `sso:account:access`)
*(Your browser will open to authenticate. Allow the request.)*
- **AWS account**: Select the new 12-digit account ID for `oversight-test`
- **Role**: `AdministratorAccess`
- **Default client Region**: `us-east-1`
- **CLI default output format**: `json`
- **Profile name**: `oversight-test`

### Step 3.2 — Login and verify identity (read-only)

```bash
aws sts get-caller-identity --profile oversight-test
```

Expected output — `Account` must be your new `oversight-test` account (not `975050146846`):
```json
{
    "Account": "<NEW_ACCOUNT_ID>",
    "Arn": "arn:aws:sts::<NEW_ACCOUNT_ID>:assumed-role/AWSReservedSSO_AdministratorAccess_.../danivpv"
}
```

---

## Phase 4 — Seeding the FAISS Index (Local -> Local)

Before deploying, we generate the vector embeddings locally and store them in the `assets/index/` directory.

> [!IMPORTANT]
> Your AWS account must have Bedrock model access enabled for **Titan Embeddings v2** and **Claude 4.5 Haiku**. 

Run the ingestion script:
```bash
make seed
```

**What this does:**
1. Loads PDFs from `scripts/input/`
2. Chunks them locally
3. Calls AWS Bedrock (Titan v2) to embed the chunks
4. Builds a local FAISS index (`assets/index/index.faiss`) and metadata pickle (`assets/index/index.pkl`)

## Chunking Strategy Rationale

Based on analysis of the three PDFs in `scripts/input/`:

| Document | Pages | Avg chars/page | Character density |
|---|---|---|---|
| Qwen3 embedding paper | 14 | 2,836 | Medium (academic) |
| RAG survey (Tongji/Fudan) | 21 | 4,580 | High (dense academic) |
| McKinsey AI 2025 | 32 | 672 | Low (image-heavy report) |

**Chosen**: `chunk_size=800, chunk_overlap=150`
- Smaller than prototype's 1000/200 to keep 2–3 paragraphs coherent in the dense academic papers
- 150-char overlap prevents sentence splits at chunk boundaries
- Avoids near-empty chunks from the sparse McKinsey pages (672 chars/page < 800 chunk_size → each page becomes roughly 1 chunk)


## Phase 5 — Bootstrapping & Deployment (Local -> AWS)

We use the AWS CDK to deploy the infrastructure. 

### Step 5.1 — Bootstrap CDK
If this is your first time deploying CDK to this account/region, bootstrap it:
```bash
uv run cdk bootstrap aws://<YOUR_ACCOUNT_ID>/us-east-1
```

### Step 5.2 — Deploy the Stateful Stack (S3)
This creates the S3 bucket and automatically zips and uploads the `assets/index/` folder created in Phase 1.
```bash
make deploy-stateful
```

### Step 5.3 — Deploy the Stateless Stack (Lambda & API)
This builds the Docker image, pushes it to ECR, and creates the Lambda function and API Gateway REST API.
```bash
make deploy-stateless
```

When finished, the terminal will print out the outputs:
```text
Outputs:
KBAgentStack.RagApiApiKeyId... = <API_KEY_ID>
KBAgentStack.RagApiApiUrl... = https://<API_ID>.execute-api.us-east-1.amazonaws.com/prod/
```

## Phase 6 — Retrieve API Key & Test

Instead of complex scripts, we manually grab the API Key using the `<API_KEY_ID>` printed in the deployment output above.

### Step 6.1 — Get the secret key value
```bash
aws apigateway get-api-key --api-key <API_KEY_ID> --include-value --query "value" --output text
```

### Step 6.2 — Test the API
Create a `.env` file in the root of the repository:
```dotenv
API_BASE_URL=https://<API_ID>.execute-api.us-east-1.amazonaws.com/prod
API_TOKEN=<THE_SECRET_KEY_VALUE_FROM_STEP_6.1>
```

Run the smoke tests:
```bash
make test-api
```

Expected output:
```
TEST: 01_health
  GET .../health     ►  200  (312 ms)   [PASS]

TEST: 02_auth_rejection
  POST .../query (no key)  ►  403  (89 ms)    [PASS]

TEST: 03_authenticated_query
  POST .../query (with key) ► 200  (8421 ms)  [PASS]
  Answer:     Retrieval-Augmented Generation (RAG) is...
  Confidence: 0.82   Sources: 5 chunk(s)
```

> [!TIP]
> The first query is slow (~8–15s) due to Lambda cold starts (downloading the FAISS index from S3 and spinning up the container). Subsequent queries will take ~2–4s.



## Upgrade Path

| Current | Production upgrade | What changes |
|---|---|---|
| API Key auth | Cognito JWT Authorizer | CDK only; Lambda unchanged |
| Lambda | Fargate | Same Dockerfile; `uvicorn main:app` instead of Mangum |
| Manual deploy | CodePipeline toolchain | Add `toolchain.py`; CDK app unchanged |
| x86_64 | ARM64 Graviton (~20% cheaper) | Verify faiss-cpu ARM wheel; one CDK param change |

# AWS Native Knowledge Base Agent

A production-ready RAG prototype built entirely on AWS native services — demonstrating **architecture judgment**, **infrastructure-as-code quality**, and **robust RAG design** within an 8-12 hour, $20 budget constraint.

---

## Presentation Guide

What we will walk through today, ordered for maximum impact:

1. **[Architecture Comparison](1-analysis/02_Architecture_Comparison.md)** — The decision
    - Four options evaluated: Lambda, Fargate, Bedrock Knowledge Bases, AgentCore
    - Chosen: **Lambda + REST API Gateway** — best rubric alignment, lowest risk, clearest production path
    - Key tradeoffs: REST vs HTTP/2 API auth story, FAISS in-memory vs managed vector store, $1-2 total cost

2. **[Implementation Reference](3-operations/03_Implementation_Reference.md)** — How it's built
    - Two-stack CDK design: **Stateful** (S3) + **Stateless** (Lambda + API Gateway)
    - Docker Lambda with `uv` multi-stage build — bypasses 250MB limit, deterministic installs
    - Mangum ASGI bridge: FastAPI routes running natively on Lambda
    - ETag-based FAISS warm-start cache: index only re-downloaded when S3 object changes

3. **[Deployment Guide](3-operations/07_Deployment_Guide.md)** — Proof it runs `*`
    - Live deploy into a dedicated `oversight-test` AWS SSO member account
    - `make seed` → `make deploy` → `make streamlit` — end-to-end in 4 commands
    - Evidence: CloudWatch logs, API Gateway access logs, request IDs

4. **[Evaluation](3-operations/08_Evaluation.md)** — Does the RAG actually work?
    - 7 real queries across 3 documents (RAG survey, McKinsey AI report, LlamaIndex paper)
    - Demonstrates: strong grounding, proper uncertainty/fallback, "lawful good" out-of-domain handling
    - Honest: surfaces real failure modes (citation chunk pollution, PDF table parsing) + improvement plan

5. **[Road to Production](3-operations/09_Road_to_Production.md)** ⭐ — The most important section
    - Lambda → Fargate migration path when streaming or cold-start latency matter
    - Zero-trust security: Cognito, Bedrock Guardrails, least-privilege IAM
    - FinOps: Bedrock token cost controls, S3 lifecycle policies
    - Platform engineering: Domain-Driven Design team boundaries, CI/CD, X-Ray observability

---

## Implemented Architecture

```mermaid
flowchart TB
    subgraph "Local Machine"
        ST[Streamlit Client<br/>reads API_URL + API_TOKEN<br/>from .env]
    end

    subgraph "AWS Cloud"
        subgraph "API Layer"
            APIGW[API Gateway REST API<br/>+ API Key Auth (x-api-key)<br/>/health  /query<br/>CloudWatch Access Logs]
        end

        subgraph "Compute Layer"
            LF[Lambda Function<br/>Docker Image via ECR<br/>FastAPI + Mangum<br/>1024MB / 30s timeout]
        end

        subgraph "AI/ML Layer"
            BE[Bedrock Claude 4.5 Haiku<br/>Answer Generation<br/>temp=0.1, max_tokens=1024]
            BT[Bedrock Titan Embed v2<br/>512 dims / normalize=True]
        end

        subgraph "Storage Layer"
            S3[S3 Bucket<br/>/documents/<br/>/index/  ← FAISS artifacts]
        end

        CW[CloudWatch Logs<br/>Structured JSON]
    end

    ST -->|HTTPS + x-api-key| APIGW
    APIGW --> LF
    LF -->|ETag check → GetObject| S3
    LF -->|InvokeModel| BT
    LF -->|InvokeModel| BE
    LF -->|Structured logs| CW
```

**CDK Stack Layout:**

| Stack | Resources | Removal Policy |
|-------|-----------|----------------|
| `KBAgentStatefulStack` | S3 bucket, bucket policy | `RETAIN` (protects data) |
| `KBAgentStatelessStack` | Lambda (ECR image), API Gateway, IAM roles, Usage Plan, CloudWatch | `DESTROY` |

---

## Run Instructions

### Prerequisites
- Python 3.12+ with `uv` installed
- AWS CLI configured (`aws configure --profile oversight`)
- Docker running (Lambda image build)
- Node.js + CDK CLI (`npm install -g aws-cdk`)

### Four-Command Deploy
```bash
make seed              # 1. Embed docs locally → upload FAISS index to S3
make deploy-stateful   # 2. Provision S3 bucket (stateful stack)
make deploy-stateless  # 3. Build Docker image → ECR → Lambda + API Gateway
make streamlit         # 4. Start local UI → point at deployed API
```

### Environment Variables
```env
AWS_PROFILE=oversight
AWS_REGION=us-east-1
API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/
API_TOKEN=<key-from-cdk-output>
```

### Example API Call
```bash
curl -X POST \
  -H "x-api-key: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is retrieval augmented generation?"}' \
  $API_URL/query
```

### Cleanup
```bash
make teardown
```
!!! warning "Manual Cleanup"
    The `KBAgentStatefulStack` S3 bucket has `removal_policy=RETAIN` to prevent data loss. After `cdk destroy`, manually delete the bucket from the AWS Console to avoid ongoing storage costs.

---

## Engineering Decisions & Tradeoffs

- **Infrastructure over Code Purity**: Clean CDK constructs with least-privilege IAM over textbook abstraction layers.
- **Serverless First**: Lambda for zero idle cost. Clear documented upgrade path to ECS Fargate when cold starts or streaming matter.
- **REST API over HTTP API v2**: Native API Key + Usage Plan support (`x-api-key` header) vs. HTTP API requiring a custom Lambda Authorizer. Upgrade path: swap to Cognito JWT authorizer on HTTP API for production.
- **`uv` + Docker Lambda**: Deterministic installs, multi-stage build cache, no 250MB zip size gamble.
- **FAISS over Managed Vector DB**: Zero per-hour cost, full control over retrieval parameters. Upgrade path: pgvector on Aurora Serverless or Pinecone when horizontal scaling is needed.

---

> For the full enterprise scaling analysis — team boundaries, security, FinOps, and DevOps — see **[Road to Production →](3-operations/09_Road_to_Production.md)**

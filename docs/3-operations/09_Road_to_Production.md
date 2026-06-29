# Road to Production

*A Systems Engineering Perspective on Scaling the RAG Architecture*

---

## 1. Executive Summary

The current architecture (Phase 0) provides a robust, serverless foundation demonstrating core Retrieval-Augmented Generation (RAG) capabilities using AWS CDK, API Gateway, Lambda, and Amazon Bedrock. While this implementation is pragmatic and adheres to a "Keep It Simple" philosophy, taking it to enterprise production requires structural shifts in how we handle platform boundaries, team responsibilities, security, and operational readiness. 

This document outlines the upgrade path to a hardened, compliant, and scalable production system.

## 2. Architecture Evolution

Our initial choices optimized for low mental overhead and rapid validation. Moving to production involves conscious decoupling:

*   **Compute Layer**: 
    *   *Current*: AWS Lambda. Great for spiky, low-volume traffic. Each Lambda container handles **one request at a time**; concurrency is achieved by AWS spinning up additional containers in parallel.
    *   *Production Triggers to migrate to **Amazon ECS on AWS Fargate***:
        *   **Traffic & Concurrency**: Fargate runs a persistent FastAPI/Uvicorn server. Because Uvicorn is async, a single container handles hundreds of concurrent requests simultaneously — waiting on Bedrock's network I/O does not block the event loop. This is far more cost-efficient than paying for N Lambda environments all waiting on the LLM.
        *   **Cold Starts**: Lambda cold starts with Docker images + FAISS index load can reach 8-15s. Fargate keeps the process warm and the index in memory across all requests.
        *   **Memory & Payload Constraints**: Lambda caps at 10GB RAM and 6MB synchronous payload. Fargate tasks can scale to 120GB RAM and remove payload size constraints — critical for local embedding models or large document uploads.
        *   **Protocol & Streaming**: REST API Gateway buffers the full response before returning it. Fargate behind an ALB supports native chunked HTTP/1.1 and HTTP/2 streaming (Server-Sent Events), dramatically improving perceived latency for LLM token generation.
        *   **VPC & Networking**: If the production architecture requires connections to on-premises databases via Direct Connect, or needs a static outbound NAT IP for third-party vendor whitelisting, Fargate is the standard pattern. Lambda VPC cold starts, though improved, add complexity.
    *   *Migration cost*: The same `Dockerfile` is used. Code change is replacing `Mangum(app)` with `uvicorn main:app` as the entrypoint. CDK changes are isolated to `ComputeConstruct`.
*   **Vector Storage**:
    *   *Current*: In-memory/local FAISS or basic retrieval for prototyping.
    *   *Production*: Transition to **Amazon OpenSearch Serverless** (Vector Engine) or **Pinecone/Milvus** for distributed, persistent, and highly scalable similarity search.
*   **Orchestration**:
    *   *Current*: Custom Python logic in Lambda.
    *   *Production*: Evaluate **Amazon Bedrock Knowledge Bases / Agents** to offload the heavy lifting of orchestration, chunking, and index syncing to AWS managed services, reducing our custom code surface area.

## 3. Platform Boundaries & Account Strategy

A single AWS account is an anti-pattern for production. Proposal of a multi-account strategy using AWS Organizations.

*   **Workload Isolation**: Separate `Dev`, `Staging`, and `Prod` accounts to contain blast radiuses. 
*   **Shared Services Account**: Hosts CI/CD pipelines (e.g., GitHub Actions runners or CodePipeline), artifact repositories (ECR), and shared DNS/routing.
*   **Network Perimeter**: The production architecture will be deployed within a VPC. We will utilize **VPC Endpoints (PrivateLink)** for Amazon Bedrock, S3, and DynamoDB. PrivateLink creates a private network interface in your VPC that routes traffic to the AWS service over the AWS backbone network — no traffic between the compute layer and ML models traverses the public internet, eliminating the exposure to internet-based threats and reducing data transfer costs.

## 4. Team Boundaries & Domain Ownership

To scale development, we must decouple the architecture to align with Conway's Law. Per [AWS CDK best practices](https://aws.amazon.com/blogs/devops/best-practices-for-developing-cloud-applications-with-aws-cdk/), teams should own their own CDK stacks — *"divide into repositories based on code lifecycle or team ownership"*. Three natural team boundaries emerge:

*   **Platform / Infrastructure Engineering**: Owns the VPC, multi-account organization structure, IAM permission boundaries, shared ECR, and the CI/CD pipeline (CodePipeline or GitHub Actions). They publish foundational CDK constructs as a versioned internal library for other teams to consume.

*   **ML / AI Engineering** *(our team — Data Scientists + ML Engineers)*: Owns the `src/rag/` monorepo. The CDK infrastructure stacks (`infrastructure.py` files) are owned by ML Engineers; the runtime business logic (`services/`, `main.py`) is owned by Data Scientists. This maps cleanly to CODEOWNERS rules:
    ```
    # .github/CODEOWNERS
    src/rag/*/infrastructure.py   @ml-engineers
    src/rag/rag/runtime/          @data-scientists
    src/rag/ingestion/            @data-scientists
    ```
    Branch protection rules enforce **linear history** (no merge commits), **required reviews** from both a Data Scientist and an ML Engineer for changes touching both runtime and infra, and **status checks** (linting, unit tests) before merge.
    
    **Distributable Package**: The core RAG runtime (`src/rag/rag/runtime/services/`) is structured as a distributable Python package. It can be published to a private **AWS CodeArtifact** PyPI index, allowing the Product Engineering team to consume the RAG logic as a versioned dependency without owning the implementation. This enforces a clean service boundary: Product Engineering consumes the API contract, not the source.

*   **Product Engineering**: Owns the Streamlit client and any future web frontend. They consume the stable `/query` API contract. They do not own any CDK stacks — they call the deployed API endpoint.

**Data Ingestion Ownership — An Open Question**: In this prototype, ingestion is an offline `make seed` script owned by Data Scientists. In production, this subsystem grows significantly and raises cross-team ownership questions:

*   **Multimodality**: Production documents include PDFs with embedded images, tables, and charts. The prototype's `PyPDFLoader` misses image content (as shown in evaluation). A proper ingestion pipeline requires a multimodal parser (e.g., Amazon Textract for tables/forms, or a vision model for figure captions).
*   **Authentication & Authorization**: Who can ingest which documents? An S3 bucket with `s3:PutObject` delegated via pre-signed URLs to authorized users (scoped by Cognito identity) is the standard pattern. The ingestion pipeline must tag documents with the uploader's identity for downstream ABAC filtering.
*   **Scale**: For large document sets, ingestion is a batch pipeline (not a Lambda). This is a natural fit for **AWS Batch** or **Step Functions** with ECS Fargate tasks, coordinated via an SQS queue that triggers on S3 `ObjectCreated` events.
*   **Team Ownership**: If ingestion becomes a product feature (user-facing upload), Product Engineering co-owns the upload API. If it remains a data pipeline, it stays with ML/AI Engineering. This ownership decision should be made explicit before the feature is built.

## 5. Security & Compliance

Security is a set of **guiding principles and policies** that must be gathered from stakeholders and encoded into the architecture before any production workload goes live. The brief explicitly calls out: *"how unauthorized calls are rejected"*, *"no plaintext secrets committed"*, and *"what you would improve for a production identity model"* (Brief §7). Our proposed guiding principles:

**Principle 1 — Zero Trust on Identity**: No user or service is trusted by default, regardless of network location.

*   Replace API Gateway API Keys with **Amazon Cognito** (or Enterprise SSO via AWS IAM Identity Center with SAML/OIDC federation). Every JWT token carries the user's identity, enabling fine-grained Attribute-Based Access Control (ABAC) — users only retrieve documents they have permission to view. The Cognito JWT Authorizer is a CDK-only change; the Lambda function is unchanged.
*   Service-to-service calls (e.g., Lambda → Bedrock) already use IAM roles with least-privilege scoped policies. In production, these roles should be constrained further with **IAM Permission Boundaries** set by the Platform Engineering team at the AWS Organizations level.

**Principle 2 — Defense in Depth on Data**:

*   All data at rest (S3, Vector DB, DynamoDB) must be encrypted using **Customer Managed Keys (CMKs)** in AWS KMS, giving the security team cryptographic control independent of AWS.
*   Implement **Amazon Macie** on the ingestion S3 buckets to automatically detect and alert on sensitive data (PII, credentials) before it is embedded into the Vector DB — a critical safeguard for enterprise knowledge bases containing internal documents.

**Principle 3 — AI-specific Guardrails**: Integrating guardrails means connecting to external safety services rather than reimplementing safety logic within our own CDK stacks.

*   **Amazon Bedrock Guardrails**: Enforce content policies, automatically redact PII from user prompts and LLM responses, and block prompt injection attacks. This is configured at the Bedrock API call level — one parameter change in `generator.py`.
*   **Organization-level Enforcement**: Use **AWS Service Control Policies (SCPs)** at the AWS Organizations level to enforce hard limits across all accounts — e.g., prevent any IAM role from disabling CloudTrail, or block deployment of unapproved Bedrock model IDs. SCPs are the security team's veto power and cannot be overridden by individual account administrators.
*   **Pre-deployment Validation**: Use **CDK Aspects** (the CDK native hook that runs during synthesis) or **CFN Guard** rules to make assertions about infrastructure properties *before* deployment. For example: assert no S3 bucket has `public_read_access=True`, assert all Lambda functions have X-Ray tracing enabled, assert all API Gateway stages have throttling configured. This catches security regressions at `cdk synth` time, not at runtime.

## 6. FinOps & Cost Management

Generative AI workloads can spiral out of budget if not strictly monitored.

*   **Token Tracking & Chargeback**: Implement a DynamoDB table to log token usage (prompt and completion tokens) per request, tagged with the `tenant_id` or `user_id`. This enables cost allocation and chargeback to specific business units.
*   **Rate Limiting**: Enforce strict Quotas and Usage Plans at the API Gateway layer to prevent abuse and manage API spend.
*   **Cost Allocation Tags**: Every CDK resource must be tagged (e.g., `Environment: Prod`, `CostCenter: AI-Ops`, `Service: KBAgent`). Use AWS Cost Explorer to monitor daily spend against anomalies.

## 7. Operational Readiness & Observability

"You cannot operate what you cannot observe." The production system must be highly observable. The current implementation already emits structured JSON logs to CloudWatch — the foundation is in place.

*   **Distributed Tracing — AWS X-Ray**: X-Ray is an AWS-native distributed tracing service. When enabled on Lambda and API Gateway, every incoming request generates a **trace** — a hierarchical timeline of every downstream call (S3 `GetObject`, Bedrock `InvokeModel`, etc.) with exact latencies. You can visualize the full RAG pipeline latency breakdown: how long FAISS search took vs. how long Claude Haiku took to respond. X-Ray integrates with OpenTelemetry, so traces can be forwarded to third-party APM tools if needed. Enabling it is a single CDK property: `tracing=lambda_.Tracing.ACTIVE`.

*   **Structured Logging — CloudWatch Logs Insights**: Our implementation already outputs structured JSON. In production, every log line should include `trace_id`, `user_id`, `session_id`, `retrieved_chunk_ids`, and `confidence_score`. This makes CloudWatch Logs Insights queries powerful — you can answer "for all queries where confidence < 0.5, what were the retrieved chunks?" in seconds.

*   **Alarms & Dashboards — CloudWatch**: A CloudWatch Dashboard tracks key RAG pipeline metrics: API Latency (p90, p99), Lambda cold start frequency, Bedrock throttling exceptions (`ThrottlingException` count), and empty retrieval rates (confidence == 0). CloudWatch Alarms trigger SNS notifications (→ PagerDuty, Slack) for elevated 5xx error rates or unexpected spikes in Bedrock token consumption.

*   **Application Error Tracking — Sentry**: For a production service, **Sentry** is worth considering alongside CloudWatch. While CloudWatch excels at infrastructure metrics and log aggregation, Sentry specializes in **application-level error tracking**: it captures Python exceptions with full stack traces, groups recurring errors by fingerprint, tracks error rates and affected users, and integrates with GitHub to link errors to commits. The trade-off is cost and added complexity. For a small team, CloudWatch Logs Insights covers most debugging needs. Sentry becomes compelling when you need to triage user-facing errors quickly without writing log queries.

*   **Feedback Loops**: Implement a `/feedback` endpoint. The client UI captures user thumbs-up/down signals. This data flows via **Amazon Kinesis Data Firehose** into an S3 data lake, enabling offline evaluation of RAG quality, drift detection in retrieval performance, and continuous prompt refinement by the Data Science team.

*   **CI/CD & Infrastructure Validation**: Enforce **`cdk-nag`** in the CI pipeline. `cdk-nag` is an open-source AWS library that runs as a CDK Aspect during `cdk synth`, statically analyzing the generated CloudFormation template against security rule packs (e.g., AWS Solutions, NIST 800-53). It fails the build if, for example, an IAM policy contains wildcards or an S3 bucket lacks encryption. This creates a security gate before any infrastructure reaches the deployment stage.

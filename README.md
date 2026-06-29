# AWS Native Knowledge Base Agent

This project demonstrates a production-ready prototype of a Retrieval-Augmented Generation (RAG) system built entirely on AWS native services. It prioritizes architecture judgment, minimal mental overhead, and robust infrastructure as code (IaC) using AWS CDK.

## Architecture Summary

The solution utilizes a serverless architecture optimized for simplicity and scalability:
*   **API Layer**: Amazon API Gateway provides a secure REST API.
*   **Compute**: AWS Lambda handles orchestration, prompt construction, and interaction with the LLM.
*   **Storage**: Amazon S3 is used for document storage.
*   **AI/ML**: Amazon Bedrock provides access to foundation models (e.g., Anthropic Claude, Amazon Titan) for embeddings and text generation.
*   **Client**: A local Streamlit application serves as the UI for interacting with the backend.

### Architecture Flow
1. **User Query**: The user inputs a question via the local Streamlit UI.
2. **API Request**: The Streamlit app makes an authenticated REST call to API Gateway.
3. **Compute Orchestration**: API Gateway invokes the AWS Lambda function.
4. **Retrieval**: Lambda fetches relevant context from the vector knowledge base (powered by FAISS locally for Phase 0, or Bedrock Knowledge Bases).
5. **Generation**: Lambda constructs an augmented prompt with the retrieved context and calls Amazon Bedrock.
6. **Response**: The grounded answer, along with source citations and metadata, is returned to the client and displayed.

## Included Sample Documents
The `docs/` folder contains extensive project documentation, which doubles as our sample knowledge base. These markdown files outline our architecture, road to production, and evaluation criteria.
*(Note: A full automated document ingestion workflow is intentionally out of scope for this prototype, adhering to the project brief constraints. Documents are processed and indexed during the `seed` phase.)*

## Run Instructions

### Prerequisites
*   Python 3.12+ and `uv` installed.
*   AWS CLI configured with appropriate credentials.
*   Node.js installed (for AWS CDK).
*   AWS CDK installed for deployment.

### Local Setup
1. **Install Dependencies**:
   ```bash
   uv sync
   ```
2. **Environment Variables**:
   Copy `.env.example` to `.env` and fill in your details:
   ```env
   # AWS API Gateway Endpoint
   API_BASE_URL=https://<your-api-id>.execute-api.us-east-1.amazonaws.com/prod
   API_TOKEN=<your-api-key>
   AWS_PROFILE=default
   ```

### Deployment (AWS CDK)
1. **Synthesize the templates**:
   ```bash
   make synth
   ```
2. **Seed the Knowledge Base**:
   ```bash
   make seed
   ```
3. **Deploy Storage Stack (Stateful)**:
   ```bash
   make deploy-stateful
   ```
4. **Deploy Application Stack (Stateless)**:
   ```bash
   make deploy-stateless
   ```
   *Note the API Gateway URL output at the end of the deployment.*

### Running the Client
Start the local Streamlit application:
```bash
make streamlit
```

### Viewing Documentation (MkDocs)
To view the comprehensive documentation, including the "Road to Production", serve the docs locally:
   ```bash
   make docs
   ```

### Cleanup
To tear down all AWS resources and avoid ongoing costs:
```bash
make teardown
```
*Note: S3 buckets created with `termination_protection=True` or `removal_policy=RETAIN` may require manual deletion.*

## Engineering Decisions & Tradeoffs
*   **Infrastructure over Code Purity**: Focused on clean, secure CDK constructs and least-privilege IAM policies.
*   **Serverless First**: Used Lambda and API Gateway for the lowest possible idle cost during prototyping. Long-term, moving to ECS Fargate is recommended if generation latency regularly exceeds API Gateway limits.
*   **API Gateway (REST vs HTTP/2)**: We explicitly chose REST API over the newer (and cheaper) HTTP API. REST APIs provide native support for API Keys and Usage Plans via header tokens (`x-api-key: <token>`). HTTP APIs require a custom Lambda Authorizer for API keys, adding orchestration overhead. 
    *   *Example (Current)*: `curl -H "x-api-key: my-secret-token" https://api.execute-api.us-east-1.amazonaws.com/prod/query`
    *   *Example (Future)*: When upgrading to HTTP API in production, we will swap to JWT tokens via Cognito (`curl -H "Authorization: Bearer <jwt>" ...`), removing the need for API keys.
*   **Tooling**: Adopted `uv` as the strict package manager to ensure deterministic, universal across OS, and lightning-fast Python environments, completely avoiding native `pip`/`venv` issues.

For an in-depth analysis of scaling this architecture, platform boundaries, security, and FinOps, please read [Road to Production](docs/3-operations/09_Road_to_Production.md).

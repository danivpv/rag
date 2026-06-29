# 3. Operations: Execution & Maturity

Welcome to the Operations phase. This section contains the definitive implementation artifacts, deployment instructions, and evaluation records for the AWS Knowledge Base Agent. It serves as both the technical blueprint of the completed work and the forward-looking roadmap for enterprise scaling.

!!! note "Evaluation Alignment"
    This section heavily targets the core deliverables and evaluation rubrics from the Project Brief, specifically:
    
    - **Infrastructure Quality:** Usable CDK, reproducible setups, and deep-dives into Lambda containerization.
    - **API Design & Integration:** Clean request schemas (Mangum + FastAPI) and authenticated Streamlit interactions.
    - **RAG & Agent Evaluation:** Measuring grounding, retrieving useful sources, and safely handling uncertainty/hallucination risks.
    - **Production-Readiness Thinking:** Security boundaries, FinOps cost optimizations, and multi-account DevOps strategies.


## Documents in this Section

### [03. Implementation Reference](03_Implementation_Reference.md)
The comprehensive technical blueprint of the repository. It maps the AWS-recommended monorepo structure and details critical architectural implementations.

*   **Key Topics:**
    * [Stateful/Stateless Stack Splitting](03_Implementation_Reference.md#2-cdk-stack-design-statefulstateless-split) (preventing S3 data loss)
    * The `uv`-powered [Docker Lambda multi-stage build cache](03_Implementation_Reference.md#4-docker-lambda-packaging-decision)
    * [Mangum ASGI adapter](03_Implementation_Reference.md#5-why-mangum) translating API Gateway payloads to FastAPI
    * Deep-dive into the [FAISS IndexFlatIP memory cache logic](03_Implementation_Reference.md#subsystem-2-computeconstruct-srcragraginfrastructurepy) (including the mathematical rationale for cosine similarity).

### * [07. Deployment Guide](07_Deployment_Guide.md)
A rigorous, step-by-step runbook for deploying the infrastructure into a fresh AWS environment.

*   **Key Topics:**
    * [Creating a dedicated AWS SSO member account](07_Deployment_Guide.md#phase-1-create-the-member-account-console) (`oversight-test`)
    * [Managing cross-profile AWS CLI credentials](07_Deployment_Guide.md#phase-3-configure-the-cli-profile)
    * Running the offline [FAISS seeding script](07_Deployment_Guide.md#phase-4-seeding-the-faiss-index-local-local) (`make seed`) with chunking rationale
    * Executing [CDK bootstrapping](07_Deployment_Guide.md#phase-5-bootstrapping-deployment-local-aws) and testing the live API endpoints.

### [08. Evaluation](08_Evaluation.md)
A lightweight but strict evaluation matrix testing the RAG agent against real-world query scenarios.

*   **Key Topics:**
    * [Detailed Examples](08_Evaluation.md#3-detailed-examples) Assessing whether answers are grounded in context, the usefulness of retrieved sources, and the accuracy of confidence scores. 
    * It explicitly highlights ["Lawful Good" behavior](08_Evaluation.md#example-c-good-uncertainty-handling) where the model safely admits "I don't know" when faced with out-of-domain queries or poor retrieval, avoiding hallucination.

### [09. Road to Production](09_Road_to_Production.md)
The crown jewel of the submission. A Staff/Principal Systems Engineer perspective on graduating this prototype to an enterprise-grade workload.

*   **Key Topics:**
    * [Upgrading the compute layer](09_Road_to_Production.md#41-compute-layer-lambda-to-ecs-fargate) from Lambda to ECS Fargate
    * Establishing [Team/Platform boundaries](09_Road_to_Production.md#7-platform-engineering-team-boundaries) via Domain-Driven Design (Conway's Law)
    * [Zero-Trust security](09_Road_to_Production.md#5-security-compliance-zero-trust) with Amazon Cognito and Bedrock Guardrails
    * [Observability](09_Road_to_Production.md#6-observability-finops) via AWS X-Ray and structured CloudWatch logging.

# 2. Strategy: Execution & Management

Welcome to the Strategy phase. This section covers the project management, prioritization, and meta-level tooling strategies used to deliver the AWS Knowledge Base Agent within the constraints of an 8-12 hour window and a $20 budget.

!!! note "Architecture Choices"
    This section directly aligns with the evaluation criteria from the Project Brief, specifically:
    
    - **Architecture Decision:** We elected to adopt the **Suggested Architecture** (Local Streamlit client → API Gateway → Lambda/FastAPI → S3/FAISS) outlined in the brief. This aligns with a "Keep It Simple" philosophy, providing a clear path to production while minimizing moving parts for a prototype.
    - **Team Boundaries:** We intentionally minimized deviations from the original prototype's core RAG logic (retaining FAISS, confidence scoring, and answer generation patterns). In a real-world scenario, the ML Engineering team would refactor the infrastructure, while respecting previous work of Data Science team on the core RAG algorithms.
    - **Communication:** Documenting assumptions, constraints, and AI tool usage transparency.
    - **Code Quality:** Minimizing unnecessary complexity via strict feature prioritization.


## Documents in this Section

### [04. Project Management](04_Project_Management.md)
A detailed breakdown of scope decisions and feature prioritization. It explicitly maps delivery efforts to the evaluation rubric weights, ensuring time is spent on architecture and API design rather than out-of-scope features like document ingestion workflows. 

*   **Key Topics:**
    * [Scope Decisions](04_Project_Management.md#1-scope-decisions) (Ingestion out of scope, agentic extensions vs core quality)
    * [MoSCoW Prioritization Matrix](04_Project_Management.md#2-feature-prioritization-matrix)
    * [Risk Register](04_Project_Management.md#3-risk-register) (e.g., Lambda package size limits, cold starts)
    * [Production Improvements](04_Project_Management.md#7-what-to-document-as-production-improvements)

### * [05. Metaprompting & AI Tools](05_Metaprompting_and_AI_Tools.md)
A comprehensive guide outlining how AI assistants were leveraged to act as a force multiplier during development. This satisfies the brief's requirement to document AI tool usage. 

*   **Key Topics:**
    * [Global System Prompt](05_Metaprompting_and_AI_Tools.md#2-global-system-prompt)
    * [Thread-by-thread context injection strategies](05_Metaprompting_and_AI_Tools.md#3-metaprompting-strategy-per-thread)
    * [Transparency Guidelines](05_Metaprompting_and_AI_Tools.md#7-transparency-guidelines) on the boundaries between human architectural judgment and AI code generation.

### * [06. Blockers Today](06_Blockers_Today.md)
An operational runbook addressing immediate implementation prerequisites. 

*   **Key Topics:**
    * [AWS Credential Management](06_Blockers_Today.md#blocker-1-aws-credentials-for-clicdk-unblocked) (mixing SSO with Access Keys)
    * [Enabling Bedrock Foundation Models](06_Blockers_Today.md#blocker-2-enable-bedrock-foundation-models)
    * [CDK Bootstrapping](06_Blockers_Today.md#blocker-3-cdk-bootstrap)
    * Strategic decision to adopt [Docker-based Lambdas](06_Blockers_Today.md#blocker-4-lambda-package-size-faiss-cpu-done-decided-on-docker-deployment) to bypass the 250MB deployment limit when dealing with native libraries like `faiss-cpu`.

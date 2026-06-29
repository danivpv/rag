# 1. Analysis: Strategy & Design

Welcome to the Analysis phase of the AWS Native Knowledge Base Agent. The documents in this section provide the foundational research and strategic decision-making that drove the architecture of this project.

!!! note "Evaluation Alignment"
    This section directly addresses the core evaluation criteria from the Project Brief, specifically:
    
    - **Architecture Judgment:** Sensible AWS service choices and clear production paths.
    - **RAG Design:** Grounded responses, useful retrieval, sources, and uncertainty handling.
    - **Communication:** Assumptions, tradeoffs, and explanation of changes from the sample project.


## Documents in this Section

### * [01. Prototype Analysis](01_Prototype_Analysis.md)
An in-depth tear-down of the original local prototype. This document analyzes the monolithic Streamlit and FastAPI implementations and outlines the migration strategy to an AWS serverless architecture.

*   **Key Topics:** 
    * [RAG Pipeline Deep Dive](01_Prototype_Analysis.md#2-rag-pipeline-deep-dive) (Ingestion, Chunking, Embedding)
    * [Confidence Scoring heuristics](01_Prototype_Analysis.md#24-confidence-scoring-how-they-do-it)
    * [Prompting Strategy](01_Prototype_Analysis.md#26-prompting-strategy)
    * [Migration map to AWS](01_Prototype_Analysis.md#5-what-we-keep-vs-what-we-replace) (e.g., replacing Google Gemini with Amazon Bedrock Claude Haiku and Titan Embeddings).

### [02. Architecture Comparison](02_Architecture_Comparison.md)
A comprehensive decision matrix evaluating different architectural approaches for the Knowledge Base Agent, strictly bound by the $20 budget and 8-12 hour timeframe constraints.

*   **Key Topics:** 
    * [Architecture Alternatives Evaluation](02_Architecture_Comparison.md#1-architecture-options-overview)
    * [Budget Analysis ($20 Limit)](02_Architecture_Comparison.md#3-budget-analysis-20-limit)
    * [Authentication Tradeoffs](02_Architecture_Comparison.md#4-authentication-tradeoffs) (REST API Keys vs. HTTP API JWTs)
    * [Fargate Containers + Vector DB Statelessness](02_Architecture_Comparison.md#5-fargate-containers--vector-db-statelessness) on ephemeral compute
    * [Streaming Paths (Response Streaming)](02_Architecture_Comparison.md#6-streaming-paths-response-streaming)
    * [Embedding Service Choice](02_Architecture_Comparison.md#7-embedding-service-choice)
    * [Detailed Evaluation Matrix](02_Architecture_Comparison.md#8-detailed-evaluation-matrix)

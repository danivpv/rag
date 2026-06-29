# 10. RAG & API Implementation Notes

This document explicitly addresses the evaluation criteria outlined in Sections 7 and 9 of the Project Brief, detailing how the core RAG logic was adapted from the prototype and how the API client integration functions.

## 1. RAG Behavior & Mapping to Prototype

We explicitly chose to retain the core RAG logic from the provided prototype (FAISS, confidence scoring, answer generation patterns). This decision respects cross-functional team boundaries: the ML Engineering team refactors the infrastructure while the Data Science team maintains ownership of the RAG algorithms.

### 1.1 Document Ingestion & Seeding
- **Sample Documents**: The solution uses the three sample PDFs provided in `scripts/input/` (a Qwen paper, an academic survey on RAG, and a McKinsey AI report).
- **Seeding the Knowledge Base**: Document ingestion is performed locally via the `make seed` script. This script loads the PDFs, chunks them, calls Amazon Bedrock (Titan v2) to generate embeddings, and builds a local FAISS index. The CDK stack then zips and uploads this index to S3 during deployment.
- **Why Ingestion is Out of Scope**: A dynamic, user-facing ingestion endpoint is intentionally excluded. Building a secure ingestion pipeline requires asynchronous batch processing (e.g., Step Functions or AWS Batch), multi-modal parsers, and strict S3 presigned URL authorization. A synchronous Lambda endpoint cannot safely handle multi-megabyte PDF uploads and embedding generation within standard API timeout windows.

### 1.2 Chunking & Indexing
- **Parsing**: We migrated from the prototype's parser to LangChain's `PyPDFLoader` to simplify extraction.
- **Strategy**: Based on document density analysis, we tuned the strategy to `chunk_size=800` and `chunk_overlap=150`. This prevents sentence splits at boundaries and accommodates the dense academic papers better than the prototype's generic 1000/200 split.
- **Embedding**: Text chunks are embedded using **Amazon Bedrock Titan Embeddings v2**.

### 1.3 Retrieval & Grounding
- **Query Processing**: The original user query is tokenized, stop-words are removed, and keywords are extracted.
- **Hybrid Retrieval Strategy**: We employ a hybrid retrieval approach ported directly from the prototype:
  1. **Over-retrieval**: We search the FAISS index to over-retrieve candidate chunks (`min(k*3, 20)` candidates) using Inner Product (IP) similarity (since our vectors are L2-normalized).
  2. **Keyword Scoring**: We calculate a keyword match score (fraction of query keywords present in the chunk).
  3. **Re-ranking**: We calculate a combined score `(0.7 * similarity_score + 0.3 * keyword_score)` and re-rank the candidates, selecting the top `k`.
- **Prompt Construction**: The top `k` chunks are concatenated into an XML-tagged context block. The prompt explicitly commands the model (Claude 3 Haiku) to cite its sources and strictly answer from the context.
- **Grounding & Sources**: The API returns a `sources` array in the JSON response, mapping directly to the chunk metadata (`source` and `chunk_index`) retrieved from FAISS.
- **Confidence & Uncertainty**: 
  - **Confidence Score**: We use the exact heuristic formula from the prototype. This measures **retrieval quality**, not LLM certainty. It blends the best similarity score (0.5), average similarity (0.3), tight cluster consistency (0.1), and keyword overlap boost (0.1), adjusted with a power-law curve (`confidence**0.9`).
  - **Fallback**: The prompt instructs the LLM that if the context does not contain the answer (or if the index is empty), it must return a strict predefined fallback response ("I don't have information about this..."), preventing hallucination.

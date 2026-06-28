"""
Pydantic request/response models for the KB Agent API.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Request ────────────────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    """POST /query request body."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language question to answer from the knowledge base.",
        examples=["What are the key findings on RAG optimization?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of document chunks to retrieve (default 5, max 20).",
    )


# ── Response sub-models ────────────────────────────────────────────────────────


class SourceDocument(BaseModel):
    """Single retrieved source chunk included in the response."""

    document_id: str = Field(description="Source filename (e.g. rag_optimization.pdf).")
    chunk_id: str = Field(
        description="Unique chunk identifier: '<filename>#<chunk_index>'."
    )
    score: float = Field(
        description="Combined hybrid retrieval score (0–1, higher is better)."
    )
    excerpt: str = Field(description="First 300 characters of the chunk content.")


class ResponseMetadata(BaseModel):
    """Request-level telemetry included in every response."""

    model: str = Field(description="Bedrock model ID used for generation.")
    retrieval_strategy: str = Field(description="Retrieval strategy identifier.")
    request_id: str = Field(
        description="UUID identifying this request for log correlation."
    )
    latency_ms: int = Field(description="End-to-end latency in milliseconds.")


# ── Response ───────────────────────────────────────────────────────────────────


class QueryResponse(BaseModel):
    """POST /query response body — matches the API contract exactly."""

    answer: str = Field(
        description="Generated answer grounded in the retrieved context."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Heuristic retrieval-quality confidence score (0–1). "
            "Based on FAISS similarity and keyword overlap — NOT LLM self-reported confidence."
        ),
    )
    sources: list[SourceDocument] = Field(
        description="Retrieved chunks used to ground the answer, sorted by score."
    )
    metadata: ResponseMetadata = Field(
        description="Request telemetry for observability."
    )

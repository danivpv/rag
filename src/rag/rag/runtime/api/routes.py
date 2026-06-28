"""
API route handlers — /health and /query.

Design decisions:
- /health returns 200 immediately without touching S3 or Bedrock.
  API Gateway health checks and Streamlit client startup probes use this.
- /query validates input via Pydantic, delegates to services, and returns
  a structured QueryResponse with latency + request_id.
- HTTPException 503 propagates cleanly (Mangum preserves status code).
- Structured logging via services.logger wraps every request with
  request_id, latency_ms, and model_id for CloudWatch correlation.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException

from .models import QueryRequest, QueryResponse, ResponseMetadata, SourceDocument
from ..services.embedder import embed_query, load_or_refresh_index
from ..services.generator import generate_answer
from ..services.logger import log
from ..services.retriever import retrieve

router = APIRouter()


# ── Health ─────────────────────────────────────────────────────────────────────


@router.get(
    "/health",
    summary="Health check",
    response_description="Returns 200 when the Lambda is reachable.",
)
def health() -> dict:
    """Lightweight liveness probe. Does NOT warm the FAISS index."""
    return {"status": "healthy"}


# ── Query ──────────────────────────────────────────────────────────────────────


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the knowledge base",
    response_description="Grounded answer with source citations and confidence score.",
)
def query(request: QueryRequest) -> QueryResponse:
    """
    Full RAG pipeline:
    1. Load (or warm-hit) the FAISS index from S3 (ETag-cached).
    2. Embed the question via Bedrock Titan Embed v2.
    3. Hybrid FAISS + keyword retrieval.
    4. Generate answer via Bedrock Claude Haiku.
    5. Return structured response with confidence score and source metadata.
    """
    request_id = str(uuid.uuid4())
    t_start = time.monotonic()

    try:
        # ── Step 1: Ensure FAISS index is loaded (ETag-cached warm hits are cheap) ──
        load_or_refresh_index()

        # ── Step 2: Embed the user's question ─────────────────────────────────────
        query_embedding = embed_query(request.question)

        # ── Step 3: Hybrid FAISS + keyword retrieval ───────────────────────────────
        retrieved_chunks = retrieve(
            question=request.question,
            query_embedding=query_embedding,
            k=request.top_k,
        )

        if not retrieved_chunks:
            # Knowledge base is empty or query produced no candidates.
            latency_ms = int((time.monotonic() - t_start) * 1000)
            log(
                level="WARNING",
                message="No chunks retrieved",
                request_id=request_id,
                question_preview=request.question[:100],
                latency_ms=latency_ms,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "No relevant documents found in the knowledge base. "
                    "Ensure the FAISS index has been seeded (scripts/seed.py)."
                ),
            )

        # ── Step 4: Generate answer via Claude Haiku ───────────────────────────────
        generation_result = generate_answer(
            question=request.question,
            retrieved_chunks=retrieved_chunks,
            request_id=request_id,
        )

        # ── Step 5: Assemble response ──────────────────────────────────────────────
        latency_ms = int((time.monotonic() - t_start) * 1000)

        sources = [
            SourceDocument(
                document_id=chunk["source"],
                chunk_id=f"{chunk['source'].rsplit('.', 1)[0]}#{chunk['chunk_index']}",
                score=round(chunk["combined_score"], 4),
                excerpt=chunk["content_preview"],
            )
            for chunk in retrieved_chunks
        ]

        response = QueryResponse(
            answer=generation_result["answer"],
            confidence=round(generation_result["confidence"], 4),
            sources=sources,
            metadata=ResponseMetadata(
                model=generation_result["model_id"],
                retrieval_strategy="faiss_hybrid_512d",
                request_id=request_id,
                latency_ms=latency_ms,
            ),
        )

        log(
            level="INFO",
            message="Query completed",
            request_id=request_id,
            question_preview=request.question[:100],
            num_sources=len(sources),
            confidence=response.confidence,
            model_id=generation_result["model_id"],
            latency_ms=latency_ms,
        )

        return response

    except HTTPException:
        # Re-raise FastAPI exceptions unchanged (preserves status code).
        raise
    except Exception as exc:
        latency_ms = int((time.monotonic() - t_start) * 1000)
        log(
            level="ERROR",
            message="Unhandled error in /query",
            request_id=request_id,
            error=str(exc),
            latency_ms=latency_ms,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

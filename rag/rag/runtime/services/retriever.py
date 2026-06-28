"""
Hybrid FAISS + keyword retrieval.

Ported from prototype retriever.py (Knowledge-Base-Agent-using-RAG/rag/retriever.py).

Key changes from prototype:
- LangChain Document objects → plain Python dicts (no LangChain in Lambda).
- vectorstore.similarity_search_with_score() → raw faiss.IndexFlatIP.search().
- FAISS IndexFlatIP returns inner-product scores (higher = more similar).
  Prototype used L2 distance (lower = more similar) and converted via
  1 - (distance/2). We work directly with IP similarity scores (already in
  0-1 range when vectors are L2-normalised with normalize=True in Titan Embed).
- Keyword match score formula is identical (word overlap / num_keywords).
- Hybrid scoring formula is identical: 0.7 * similarity + 0.3 * keyword_score.
- Over-retrieval is identical: min(k*3, 20) candidates, take top-k after scoring.

Chunk dict schema (from seed.py):
    {
        "text":         str,   # full chunk text
        "source":       str,   # filename, e.g. "rag_optimization.pdf"
        "chunk_index":  int,   # 0-based chunk position within that file
        "file_path":    str,   # optional full path (not used at query time)
    }
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .embedder import get_chunks, get_index
from .logger import log

# ── Stop words (identical to prototype retriever.py L45) ──────────────────────
_STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "may",
    "might",
    "must",
    "can",
    "this",
    "that",
    "these",
    "those",
    "what",
    "which",
    "who",
    "whom",
    "whose",
    "where",
    "when",
    "why",
    "how",
}


# ── Keyword helpers ────────────────────────────────────────────────────────────


def _extract_keywords(query: str) -> list[str]:
    """
    Extract non-stop-word tokens from the query.

    Identical to prototype retriever.py L34-L61:
    - regex word extraction (alphanumeric, hyphens, apostrophes)
    - stop-word removal
    - length filter (>2 chars)
    - deduplicate preserving order
    """
    words = re.findall(r"\b[a-zA-Z0-9\-']+\b", query.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for w in words:
        if w not in _STOP_WORDS and len(w) > 2 and w not in seen:
            seen.add(w)
            keywords.append(w)
    return keywords


def _expand_query(query: str) -> str:
    """Append extracted keywords to the query (prototype L63-L81)."""
    keywords = _extract_keywords(query)
    return f"{query} {' '.join(keywords)}" if keywords else query


def _keyword_match_score(text: str, keywords: list[str]) -> float:
    """
    Fraction of keywords appearing in the chunk text (prototype L83-L101).

    Returns 0.0 if no keywords (avoids division by zero).
    """
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


# ── Retrieval ──────────────────────────────────────────────────────────────────


def retrieve(
    question: str,
    query_embedding: np.ndarray,
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    Hybrid FAISS + keyword retrieval.

    Algorithm (mirrors prototype retrieve_with_scores L131-L206):
    1. Extract keywords from the original question.
    2. Over-retrieve: min(k*3, 20) candidates from FAISS.
    3. For each candidate compute a combined score:
           combined = 0.7 * ip_similarity + 0.3 * keyword_score
    4. Sort descending by combined score, return top-k enriched dicts.

    Args:
        question:        Original user question (used for keyword extraction).
        query_embedding: L2-normalised embedding vector, shape (1, 512).
        k:               Number of final chunks to return.

    Returns:
        List of chunk dicts enriched with retrieval scores:
        {
            "text", "source", "chunk_index", "content_preview",
            "similarity_score", "keyword_score", "combined_score"
        }
        Sorted descending by combined_score. Empty list if index has no vectors.
    """
    index = get_index()
    chunks = get_chunks()

    if index.ntotal == 0:
        log(level="WARNING", message="FAISS index is empty — no chunks to retrieve")
        return []

    keywords = _extract_keywords(question)
    retrieve_k = min(k * 3, 20)  # over-retrieve then re-rank (prototype L150)

    # FAISS search — IndexFlatIP returns inner-product scores (higher = more similar).
    scores, indices = index.search(query_embedding, retrieve_k)
    # scores/indices shape: (1, retrieve_k) — squeeze to 1D
    scores_1d: np.ndarray = scores[0]
    indices_1d: np.ndarray = indices[0]

    enhanced: list[tuple[dict, float]] = []
    for ip_score, vec_idx in zip(scores_1d.tolist(), indices_1d.tolist()):
        if vec_idx < 0:
            # FAISS returns -1 for padding when the index has fewer vectors than k
            continue

        chunk: dict = chunks[vec_idx]
        keyword_score = _keyword_match_score(chunk["text"], keywords)

        # ip_score is already in [0,1] because vectors are L2-normalised.
        # Clamp to [0,1] defensively (float rounding can push just above 1.0).
        similarity_score = max(0.0, min(1.0, float(ip_score)))
        combined_score = 0.7 * similarity_score + 0.3 * keyword_score

        enhanced.append(
            (
                {
                    **chunk,
                    "content_preview": chunk["text"][:300]
                    + ("..." if len(chunk["text"]) > 300 else ""),
                    "similarity_score": round(similarity_score, 6),
                    "keyword_score": round(keyword_score, 6),
                    "combined_score": round(combined_score, 6),
                },
                combined_score,
            )
        )

    # Sort descending by combined_score (prototype L192)
    enhanced.sort(key=lambda x: x[1], reverse=True)

    results = [chunk for chunk, _ in enhanced[:k]]

    log(
        level="INFO",
        message="Retrieval complete",
        question_preview=question[:80],
        candidates_retrieved=len(enhanced),
        top_k_returned=len(results),
        top_score=results[0]["combined_score"] if results else None,
    )

    return results


# ── Context formatting ─────────────────────────────────────────────────────────


def format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into the context string injected into the LLM prompt.

    Format mirrors prototype retriever.py L208-L228:
        [Source: {source}, Chunk {chunk_index}]
        {text}
        ---
    """
    parts: list[str] = []
    for chunk in chunks:
        source = chunk.get("source", "Unknown")
        idx = chunk.get("chunk_index", 0)
        parts.append(f"[Source: {source}, Chunk {idx}]\n{chunk['text']}\n")
    return "\n---\n\n".join(parts)

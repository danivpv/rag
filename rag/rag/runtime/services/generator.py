"""
Bedrock Claude Haiku generation + heuristic confidence scoring.

Ported from prototype generator.py (Knowledge-Base-Agent-using-RAG/rag/generator.py).

Key changes from prototype:
- genai.GenerativeModel.generate_content() → boto3 InvokeModel with Claude Messages API.
- Gemini plain-text prompt → XML-tagged Claude prompt (Claude's native format).
  XML tags reduce prompt injection risk and improve instruction-following fidelity.
- Temperature: 0.7 (prototype) → 0.1 (grounded QA; low temp reduces hallucination).
- Model: pinned via BEDROCK_GENERATE_MODEL_ID env var; no dynamic detection.
- Confidence scoring formula preserved exactly from prototype generator.py L256-L305:
      confidence = 0.5*best_similarity + 0.3*avg_similarity + 0.1*consistency + 0.1*kw_boost
      confidence = confidence**0.9   # slight power-law adjustment
      confidence = clamp(0, 1)
  Note: prototype works with L2 distance scores (lower=better, converts via 1-distance/2).
  We receive IP similarity scores (higher=better, already 0-1). The formula uses
  similarity_score directly — no conversion needed.

Claude Messages API body:
    {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0.1,
        "system": "<system prompt>",
        "messages": [{"role": "user", "content": "<user prompt>"}]
    }
"""

from __future__ import annotations

import json
import re

import boto3

from ..config import settings
from .logger import log
from .retriever import format_context

# ── Environment ────────────────────────────────────────────────────────────────
_GENERATE_MODEL_ID = settings.bedrock_generate_model_id
_BEDROCK_REGION = settings.bedrock_region

# ── Claude prompt templates ────────────────────────────────────────────────────
# XML tags are Claude's native format — they delineate context/question clearly
# and reduce prompt injection risk from document content.

_SYSTEM_PROMPT = (
    "You are a knowledge base assistant. Answer questions strictly from the provided context. "
    "If the answer is not in the context, say: "
    "'I don't have information about this in the knowledge base.' "
    "Be concise and factual."
)

_USER_PROMPT_TEMPLATE = """\
<context>
{context}
</context>

<question>
{question}
</question>

<instructions>
- Answer only from the context above. Do not use external knowledge.
- Be concise and direct.
- Cite the source document for each key claim.
</instructions>"""

_MAX_TOKENS = 1000
_TEMPERATURE = 0.1  # Low temp: grounded QA needs deterministic answers

# ── boto3 client (module-level, reused on warm invocations) ───────────────────
_bedrock = boto3.client("bedrock-runtime", region_name=_BEDROCK_REGION)


# ── Confidence scoring ────────────────────────────────────────────────────────


def _compute_confidence(
    retrieved_chunks: list[dict],
    question: str,
) -> float:
    """
    Heuristic retrieval-quality confidence score.

    Ported exactly from prototype generator.py L256-L305, adapted for IP scores.
    This is NOT LLM-reported confidence — it measures retrieval quality:
        - best_similarity:  similarity of the closest chunk (signal strength)
        - avg_similarity:   average across all chunks (context breadth)
        - consistency:      1/(1+variance) of scores (reward tight clusters)
        - keyword_boost:    word overlap between query and retrieved chunks

    The **0.9 power** compresses scores slightly toward the middle — avoids
    false 0.99 confidence while still discriminating clearly.
    """
    if not retrieved_chunks:
        return 0.0

    scores = [c["similarity_score"] for c in retrieved_chunks]
    best_similarity = max(scores)
    avg_similarity = sum(scores) / len(scores)

    if len(scores) > 1:
        variance = sum((s - avg_similarity) ** 2 for s in scores) / len(scores)
        consistency = 1.0 / (1.0 + variance)
    else:
        consistency = 1.0

    # Keyword overlap boost (prototype generator.py L276-L287)
    query_words = set(re.findall(r"\b\w+\b", question.lower()))
    keyword_matches = 0.0
    for chunk in retrieved_chunks:
        content_words = set(re.findall(r"\b\w+\b", chunk["text"].lower()))
        overlap = len(query_words & content_words)
        if overlap > 0:
            keyword_matches += overlap / len(query_words) if query_words else 0.0
    keyword_boost = min(1.0, keyword_matches / len(retrieved_chunks))

    raw_confidence = (
        0.5 * best_similarity
        + 0.3 * avg_similarity
        + 0.1 * consistency
        + 0.1 * keyword_boost
    )

    # Slight power-law adjustment (prototype L300)
    confidence = raw_confidence**0.9

    return max(0.0, min(1.0, confidence))


# ── Generation ─────────────────────────────────────────────────────────────────


def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
    request_id: str,
) -> dict:
    """
    Generate an answer using Bedrock Claude Haiku.

    Args:
        question:         User's question.
        retrieved_chunks: Enriched chunk dicts from retriever.retrieve().
        request_id:       UUID for log correlation.

    Returns:
        {
            "answer":     str,   # generated text
            "confidence": float, # heuristic score [0, 1]
            "model_id":   str,   # BEDROCK_GENERATE_MODEL_ID
        }
    """
    context = format_context(retrieved_chunks)

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        context=context,
        question=question,
    )

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": _MAX_TOKENS,
            "temperature": _TEMPERATURE,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
    ).encode("utf-8")

    log(
        level="INFO",
        message="Invoking Bedrock Claude Haiku",
        request_id=request_id,
        model_id=_GENERATE_MODEL_ID,
        num_chunks=len(retrieved_chunks),
    )

    response = _bedrock.invoke_model(
        modelId=_GENERATE_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    response_body: dict = json.loads(response["body"].read())

    # Claude Messages API returns content as a list of blocks.
    # We take the first text block (there is always exactly one for our prompt).
    answer_text: str = response_body["content"][0]["text"].strip()

    confidence = _compute_confidence(retrieved_chunks, question)

    log(
        level="INFO",
        message="Generation complete",
        request_id=request_id,
        model_id=_GENERATE_MODEL_ID,
        confidence=round(confidence, 4),
        input_tokens=response_body.get("usage", {}).get("input_tokens"),
        output_tokens=response_body.get("usage", {}).get("output_tokens"),
    )

    return {
        "answer": answer_text,
        "confidence": confidence,
        "model_id": _GENERATE_MODEL_ID,
    }

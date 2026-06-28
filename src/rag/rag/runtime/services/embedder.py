"""
Bedrock Titan Embed v2 invocation + FAISS ETag write-through cache.

Design decisions:
- Module-level globals (_index, _chunks, _cached_etag) survive Lambda warm
  invocations. On a warm hit, head_object() costs ~2ms; no S3 download occurs
  unless the ETag has changed (i.e. seed.py uploaded a new index).
- IndexFlatIP: inner-product index. Titan Embed v2 with normalize=True emits
  L2-normalised vectors, so inner product == cosine similarity. Higher score
  means more similar (opposite sign convention from L2 distance).
- We store chunk metadata separately in a pickle file (index.pkl).
  FAISS indexes do not natively store per-vector metadata; the pickle maintains
  a 1-to-1 mapping with FAISS vector positions (row i ↔ _chunks[i]).
- No LangChain: FAISS.from_documents() / load_local() replaced by raw
  faiss.read_index() and pickle.load().
- Bedrock body encoding: json.dumps → bytes → base64 is NOT needed.
  boto3 InvokeModel accepts the body as raw bytes; we pass json.dumps().encode().
"""

from __future__ import annotations

import json
import pickle

import boto3
import faiss
import numpy as np

from ..config import settings
from .logger import log

# ── Environment variables ──────────────────────────────────────────────────────
_BUCKET = settings.s3_bucket_name
_EMBED_MODEL_ID = settings.bedrock_embed_model_id
_BEDROCK_REGION = settings.bedrock_region

# ── S3 key paths (must match scripts/seed.py) ─────────────────────────────────
_INDEX_KEY = "index/index.faiss"
_PKL_KEY = "index/index.pkl"
_TMP_FAISS = "/tmp/index.faiss"
_TMP_PKL = "/tmp/index.pkl"

# ── Module-level cache (survives Lambda warm invocations) ─────────────────────
_index: faiss.Index | None = None
_chunks: list[dict] | None = None  # list of chunk dicts; index i ↔ _chunks[i]
_cached_etag: str | None = None

# ── boto3 clients (module-level = reused across warm invocations) ─────────────
_s3 = boto3.client("s3")
_bedrock = boto3.client("bedrock-runtime", region_name=_BEDROCK_REGION)


# ── Index management ───────────────────────────────────────────────────────────


def load_or_refresh_index() -> None:
    """
    Load FAISS index from S3, or serve from the module-level cache.

    ETag write-through cache pattern:
    - head_object() is cheap (~2 ms). If the ETag matches, we skip the download.
    - If the ETag changed (new index from seed.py), we re-download both files.
    - /tmp persists between warm invocations but is NOT shared across Lambda
      instances. Each cold start re-downloads regardless of ETag.
    """
    global _index, _chunks, _cached_etag

    head = _s3.head_object(Bucket=_BUCKET, Key=_INDEX_KEY)
    latest_etag: str = head["ETag"]

    if latest_etag == _cached_etag and _index is not None:
        log(level="DEBUG", message="FAISS index cache hit", etag=latest_etag)
        return  # Warm hit — index unchanged

    log(
        level="INFO",
        message="FAISS index cache miss — downloading from S3",
        etag=latest_etag,
    )

    _s3.download_file(_BUCKET, _INDEX_KEY, _TMP_FAISS)
    _s3.download_file(_BUCKET, _PKL_KEY, _TMP_PKL)

    _index = faiss.read_index(_TMP_FAISS)
    with open(_TMP_PKL, "rb") as f:
        _chunks = pickle.load(f)

    _cached_etag = latest_etag

    log(
        level="INFO",
        message="FAISS index loaded",
        num_vectors=_index.ntotal,
        num_chunks=len(_chunks),
    )


def get_index() -> faiss.Index:
    """Return the loaded FAISS index. Raises if load_or_refresh_index() not called."""
    if _index is None:
        raise RuntimeError(
            "FAISS index not loaded. Call load_or_refresh_index() first."
        )
    return _index


def get_chunks() -> list[dict]:
    """Return the chunk metadata list. Raises if load_or_refresh_index() not called."""
    if _chunks is None:
        raise RuntimeError(
            "Chunk metadata not loaded. Call load_or_refresh_index() first."
        )
    return _chunks


# ── Embedding ──────────────────────────────────────────────────────────────────


def embed_query(text: str) -> np.ndarray:
    """
    Embed a single text string using Bedrock Titan Embed v2.

    Returns:
        numpy array of shape (1, 512), dtype float32, L2-normalised.
        The (1, d) shape is required for faiss.IndexFlatIP.search().

    Titan Embed v2 parameters:
        dimensions=512: sweet spot between quality (1024) and cost (256).
        normalize=True: emits L2-normalised vectors; inner product == cosine similarity.
    """
    body = json.dumps(
        {
            "inputText": text,
            "dimensions": 512,
            "normalize": True,
        }
    ).encode("utf-8")

    response = _bedrock.invoke_model(
        modelId=_EMBED_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    embedding: list[float] = json.loads(response["body"].read())["embedding"]

    # Shape (1, 512) — FAISS search() expects a 2D array (n_queries, dim).
    return np.array([embedding], dtype=np.float32)

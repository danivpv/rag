"""
src/rag/ingestion/seed.py — Knowledge Base Ingestion Script

Loads local documents, chunks them, embeds via Amazon Bedrock Titan Embed v2,
builds a FAISS IndexFlatIP, then writes the index artifacts to a local
assets/ directory for CDK BucketDeployment to sync to S3 on deploy.

Usage:
    uv run --group data-ingestion python -m src.rag.ingestion.seed [OPTIONS]

    Or via Makefile:
        make seed

Options:
    --docs-dir PATH      Directory containing source documents [default: scripts/input]
    --assets-dir PATH    Output directory for FAISS artifacts   [default: assets/index]
    --profile NAME       AWS CLI profile to use                 [default: default]
    --region REGION      AWS region                             [default: us-east-1]
    --dry-run            Embed and build index without writing artifacts

Prerequisites:
    1. Run `uv sync --group data-ingestion` (handled by `make seed`)
    2. AWS SSO session must be active: `aws sso login --profile default`
    3. Bedrock model access enabled for amazon.titan-embed-text-v2:0 in us-east-1

Output (written to assets/index/ — picked up by CDK BucketDeployment):
    index.faiss   — raw FAISS binary (loaded by Lambda at cold start)
    index.pkl     — list[dict] chunk metadata, 1-to-1 with FAISS vector positions

Chunk dict schema (must match src/rag/rag/runtime/services/retriever.py):
    {
        "text":        str,   # full chunk text
        "source":      str,   # filename, e.g. "rag_optimization.pdf"
        "chunk_index": int,   # 0-based position within that file
    }

Design Notes:
    - FAISS index type: IndexFlatIP (inner product).
      Titan Embed v2 with normalize=True → inner product == cosine similarity.
    - Chunk size: 800 chars, overlap: 150 chars.
      Rationale: PDFs average 2.8k–4.6k chars/page (academic papers);
      800-char chunks keep ~2–3 paragraphs with 150-char overlap preventing
      sentence splits. The McKinsey report (~672 chars/page) avoids empty chunks.
    - The pickle key is "index.pkl" to match embedder.py _PKL_KEY = "index/index.pkl".
    - NO S3 upload — CDK BucketDeployment handles syncing at deploy time.
"""

from __future__ import annotations

import json
import logging
import pickle
import tempfile
from pathlib import Path
from typing import Any, Annotated

import boto3
import faiss
import numpy as np
import typer
from botocore.exceptions import ClientError
from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

app = typer.Typer(
    help="Seed the knowledge base: embed documents and write FAISS artifacts."
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed")

# ---------------------------------------------------------------------------
# Constants — must match Lambda exactly
# ---------------------------------------------------------------------------
# Embedding — must match src/rag/rag/runtime/services/embedder.py
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIMENSIONS = 512
EMBED_NORMALIZE = True

# Chunking — chosen based on PDF analysis
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# Artifacts — S3 key structure mirrors these filenames (embedder.py expects this)
FAISS_FILENAME = "index.faiss"  # → s3://bucket/index/index.faiss
PKL_FILENAME = "index.pkl"  # → s3://bucket/index/index.pkl  ← matches embedder._PKL_KEY

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_CHARS_PER_CHUNK = 8_000  # Bedrock Titan v2 safe limit


# ---------------------------------------------------------------------------
# Document loading
# ---------------------------------------------------------------------------
def load_documents(docs_dir: Path) -> list["Document"]:
    """Load all supported documents from docs_dir."""
    files = [f for f in docs_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        raise FileNotFoundError(
            f"No supported documents found in '{docs_dir}'.\n"
            f"  Supported formats: {SUPPORTED_EXTENSIONS}\n"
            "  Drop your PDF/DOCX/TXT files there and re-run."
        )

    log.info("Found %d document(s) in %s", len(files), docs_dir)
    all_docs: list[Document] = []

    for fp in sorted(files):
        ext = fp.suffix.lower()
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(str(fp))
            elif ext in {".docx", ".doc"}:
                loader = Docx2txtLoader(str(fp))
            elif ext == ".txt":
                loader = TextLoader(str(fp), encoding="utf-8")
            else:
                continue

            docs = loader.load()
            for doc in docs:
                doc.metadata.setdefault("source", fp.name)
            log.info("  Loaded %-60s  %d page(s)", fp.name, len(docs))
            all_docs.extend(docs)
        except Exception as exc:  # noqa: BLE001
            log.warning("  SKIP %s — %s", fp.name, exc)

    return all_docs


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def chunk_documents(documents: list["Document"]) -> list["Document"]:
    """Split documents into chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHUNK_SEPARATORS,
        length_function=len,
    )
    chunks = splitter.split_documents(documents)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
        if len(chunk.page_content) > MAX_CHARS_PER_CHUNK:
            chunk.page_content = chunk.page_content[:MAX_CHARS_PER_CHUNK]

    chunks = [c for c in chunks if c.page_content.strip()]
    log.info("Total chunks after splitting: %d", len(chunks))
    return chunks


# ---------------------------------------------------------------------------
# Bedrock embedding
# ---------------------------------------------------------------------------
def embed_chunks(
    chunks: list["Document"],
    session: "boto3.Session",
    region: str,
) -> "np.ndarray":
    """
    Embed each chunk using Bedrock Titan Embed Text v2.
    Returns float32 ndarray of shape (n_chunks, EMBED_DIMENSIONS).
    """
    bedrock = session.client("bedrock-runtime", region_name=region)
    embeddings: list[list[float]] = []
    total = len(chunks)

    log.info(
        "Embedding %d chunks via Bedrock Titan v2 (dimensions=%d)...",
        total,
        EMBED_DIMENSIONS,
    )

    for idx, chunk in enumerate(chunks):
        if idx % 20 == 0:
            log.info("  Progress: %d / %d", idx, total)

        body: dict[str, Any] = {
            "inputText": chunk.page_content,
            "dimensions": EMBED_DIMENSIONS,
            "normalize": EMBED_NORMALIZE,
        }
        try:
            resp = bedrock.invoke_model(
                modelId=EMBED_MODEL_ID,
                body=json.dumps(body).encode("utf-8"),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(resp["body"].read())
            embeddings.append(result["embedding"])
        except ClientError as exc:
            log.error("  Bedrock error on chunk %d: %s", idx, exc)
            raise

    log.info("  Embedding complete.")
    arr = np.array(embeddings, dtype=np.float32)
    log.info("  Embedding matrix shape: %s", arr.shape)
    return arr


# ---------------------------------------------------------------------------
# FAISS index
# ---------------------------------------------------------------------------
def build_faiss_index(embeddings: "np.ndarray") -> "faiss.IndexFlatIP":
    """Build IndexFlatIP from the embedding matrix."""
    d = embeddings.shape[1]
    index = faiss.IndexFlatIP(d)
    index.add(embeddings)  # type: ignore[arg-type]
    log.info("FAISS index built: %d vectors, dimension %d", index.ntotal, d)
    return index


# ---------------------------------------------------------------------------
# Metadata — must match Lambda chunk schema in retriever.py
# ---------------------------------------------------------------------------
def build_chunk_metadata(chunks: list["Document"]) -> list[dict[str, Any]]:
    """
    Build the list that maps FAISS index positions → chunk info.

    Key: "text" (not "page_content") — matches retriever.py chunk dict schema.
    """
    return [
        {
            "text": chunk.page_content,  # ← must be "text" for retriever.py
            "source": chunk.metadata.get("source", "unknown"),
            "chunk_index": chunk.metadata.get("chunk_index", i),
        }
        for i, chunk in enumerate(chunks)
    ]


# ---------------------------------------------------------------------------
# Write artifacts
# ---------------------------------------------------------------------------
def write_artifacts(
    index: "faiss.IndexFlatIP",
    metadata: list[dict[str, Any]],
    assets_dir: Path,
) -> None:
    """Write index.faiss and index.pkl to assets_dir."""
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Write FAISS index via temp file (faiss.write_index needs a filepath)
    faiss_path = assets_dir / FAISS_FILENAME
    with tempfile.NamedTemporaryFile(
        suffix=".faiss", delete=False, dir=assets_dir
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        faiss.write_index(index, str(tmp_path))
        tmp_path.replace(faiss_path)  # atomic rename
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    log.info("  Written: %s  (%d KB)", faiss_path, faiss_path.stat().st_size // 1024)

    # Write pickle
    pkl_path = assets_dir / PKL_FILENAME
    pkl_bytes = pickle.dumps(metadata, protocol=pickle.HIGHEST_PROTOCOL)
    pkl_path.write_bytes(pkl_bytes)
    log.info("  Written: %s  (%d bytes)", pkl_path, len(pkl_bytes))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
@app.command()
def main(
    docs_dir: Annotated[
        Path,
        typer.Option(
            "--docs-dir", help="Directory containing source documents (PDF/DOCX/TXT)."
        ),
    ] = Path("scripts/input"),
    assets_dir: Annotated[
        Path, typer.Option("--assets-dir", help="Output directory for FAISS artifacts.")
    ] = Path("assets/index"),
    profile: Annotated[
        str, typer.Option("--profile", help="AWS CLI profile for Bedrock access.", envvar="AWS_PROFILE")
    ] = "default",
    region: Annotated[
        str, typer.Option("--region", help="AWS region.", envvar="AWS_REGION")
    ] = "us-east-1",
) -> None:
    """Seed the knowledge base by chunking and embedding documents."""
    log.info("=" * 60)
    log.info("KB Agent — Knowledge Base Ingestion")
    log.info("  Profile:    %s", profile)
    log.info("  Region:     %s", region)
    log.info("  Docs dir:   %s", docs_dir)
    log.info("  Assets dir: %s", assets_dir)
    log.info("=" * 60)

    # AWS session — only needed for Bedrock embedding
    session = boto3.Session(profile_name=profile, region_name=region)

    # Verify credentials before we start embedding
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    log.info("AWS identity: account=%s", identity["Account"])

    # Pipeline
    documents = load_documents(docs_dir)
    chunks = chunk_documents(documents)
    embeddings = embed_chunks(chunks, session, region)
    index = build_faiss_index(embeddings)
    metadata = build_chunk_metadata(chunks)

    write_artifacts(index, metadata, assets_dir)

    log.info("=" * 60)
    log.info("Ingestion complete!")
    log.info("  Chunks indexed: %d", len(chunks))
    log.info("  Vectors:        %d", index.ntotal)
    log.info("  Artifacts in:   %s/", assets_dir)
    log.info("  Run `make deploy-stateful` to sync assets to S3.")
    log.info("=" * 60)


if __name__ == "__main__":
    app()

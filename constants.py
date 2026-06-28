"""
Shared constants for the KB Agent CDK app.

Centralised here so every construct/stack imports from one place.
No CDK tokens or Cfn intrinsics here — only plain Python values that are
known at synthesis time.

CDK best-practice note (https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html):
  Environment variable lookups inside Constructs/Stacks are an anti-pattern.
  This module contains ONLY Python literals (no os.environ calls) and is
  imported at the top-level app.py. Constructs receive all configuration as
  explicit constructor parameters — this file is the single synthesis-time
  source of truth, not a substitute for runtime environment variables.
"""

# ── AWS deployment target ───────────────────────────────────────────────────
REGION = "us-east-1"

# ── Top-level stack name ────────────────────────────────────────────────────
STACK_NAME = "KBAgentStack"

# ── Lambda compute sizing ───────────────────────────────────────────────────
# 1024 MB is the sweet spot: FAISS loads in ~1 s on warm start, and we stay
# well inside the $20 budget (Lambda is billed in 1-ms increments).
LAMBDA_MEMORY_MB = 1024

# 30 s covers worst-case cold start (FAISS S3 download) + Bedrock round-trip.
# API Gateway's maximum integration timeout is also 29 s, so 30 s on Lambda
# side gives us a clean "504 if Lambda times out" contract.
LAMBDA_TIMEOUT_SECONDS = 30

# ── Bedrock model IDs (us-east-1 inference profile ARNs) ───────────────────
# Use the cross-region inference profile format for Claude (required in 2024+
# for on-demand throughput; standard model IDs still work for Titan Embed).
BEDROCK_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
BEDROCK_GENERATE_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# ── FAISS index S3 key prefix ───────────────────────────────────────────────
INDEX_PREFIX = "index"
DOCS_PREFIX = "documents"

# ── API throttling ──────────────────────────────────────────────────────────
# Generous for a demo; tighten in prod once real traffic patterns are known.
THROTTLE_RATE_LIMIT = 10   # sustained requests per second
THROTTLE_BURST_LIMIT = 20  # token-bucket burst

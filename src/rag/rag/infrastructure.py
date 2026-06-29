"""
ComputeConstruct — Docker Lambda function that runs the RAG engine.

Design decisions:
- DockerImageFunction (not zip+layer): faiss-cpu must match the Lambda OS
  (Amazon Linux 2023 x86_64). Docker controls the build environment exactly
  and gives a trivial upgrade path to ECS Fargate (same Dockerfile, same code,
  just `uvicorn main:app` instead of Mangum).
- x86_64 architecture: faiss-cpu ships prebuilt x86_64 Linux wheels. ARM64
  (Graviton, ~20% cheaper) needs cross-compilation on Windows — not worth
  the risk for an 8-hour project; document as a cost optimisation.
- Memory / Timeout: see constants.py — pending calibration after RAG code is
  implemented and cold-start timing is measured.
    - 1024 MB memory: FAISS index for ~3 PDFs is <1 MB; 1 GB ensures sub-2s
      cold start and comfortable headroom for numpy/faiss operations.
    - Timeout 30 s: covers cold start + S3 download + Bedrock round-trips.
- IAM: grant_* helpers for S3; manual add_to_role_policy for Bedrock (no
  L2 helper exists yet). The stable aws_cdk.aws_bedrock module does not yet
  expose grant_invoke() helpers with least-privilege scope. Using the alpha
  package (which has grant_invoke_all_regions) would introduce unstable API
  risk and wildcards the region — worse than the manual approach here.
- BEDROCK_REGION: non-secret config, fine in env vars. Lambda reserves
  AWS_REGION — we use BEDROCK_REGION to avoid shadowing it.
"""

import os

from aws_cdk import Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk.aws_ecr_assets import Platform
from constructs import Construct

from constants import (
    BEDROCK_EMBED_MODEL_ID,
    BEDROCK_GENERATE_MODEL_ID,
    LAMBDA_MEMORY_MB,
    LAMBDA_TIMEOUT_SECONDS,
    REGION,
)

# Absolute path to the Docker build context.
# DockerImageCode.from_image_asset() needs a directory containing a Dockerfile.
# CDK runs `docker build` there at synthesis time, pushes the image to ECR,
# and injects the ECR URI into the Lambda resource.
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class ComputeConstruct(Construct):
    """Creates and owns the Docker Lambda function."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.fn = lambda_.DockerImageFunction(
            self,
            "KBAgentFn",
            code=lambda_.DockerImageCode.from_image_asset(
                _ROOT_DIR,
                file="src/rag/rag/runtime/Dockerfile",
                platform=Platform.LINUX_AMD64,
            ),
            memory_size=LAMBDA_MEMORY_MB,
            timeout=Duration.seconds(LAMBDA_TIMEOUT_SECONDS),
            environment={
                "S3_BUCKET_NAME": bucket.bucket_name,
                "BEDROCK_REGION": REGION,
                "BEDROCK_EMBED_MODEL_ID": BEDROCK_EMBED_MODEL_ID,
                "BEDROCK_GENERATE_MODEL_ID": BEDROCK_GENERATE_MODEL_ID,
            },
            description="KB Agent RAG engine — FastAPI via Mangum",
        )

        # ── Least-privilege IAM ─────────────────────────────────────────────
        bucket.grant_read(self.fn)

        # Bedrock ARN formats (verified against bedrock-test.sh model IDs):
        #   Titan Embed v2  → foundation model  → double-colon, no account segment
        #   Claude Haiku    → cross-region profile (us. prefix) → account segment required
        # Stack.of(self).account resolves to { Ref: AWS::AccountId } in the
        # CloudFormation template — strict least-privilege, no wildcards.
        # (self.account is not available on Construct, only on Stack.)
        account = Stack.of(self).account
        self.fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModels",
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:*::foundation-model/{BEDROCK_EMBED_MODEL_ID}",
                    f"arn:aws:bedrock:{REGION}:{account}:inference-profile/{BEDROCK_GENERATE_MODEL_ID}",
                    f"arn:aws:bedrock:*::foundation-model/{BEDROCK_GENERATE_MODEL_ID.replace('us.', '', 1)}",
                ],
            )
        )

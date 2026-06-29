"""
StorageConstruct — S3 bucket for FAISS index + BucketDeployment for seeding.

Design decisions:
- BucketDeployment syncs local assets/index/ into the S3 bucket at `cdk deploy`
  time. This makes seeding atomic: `make seed && make deploy-stateful` is all
  that is needed. No separate post-deploy upload step.
- assets/index/ must be populated by `make seed` (src/rag/ingestion/seed.py)
  before deploying. CDK synthesis will succeed even if the directory does not
  exist yet (BucketDeployment sources are resolved at deploy time, not synth).
- RemovalPolicy.DESTROY + auto_delete_objects: `cdk destroy` cleans up the
  bucket fully. In production, switch to RemovalPolicy.RETAIN.
- enforce_ssl=True: bucket policy denies HTTP-only requests.
  Required by the Well-Architected Security pillar.

Upgrade path to production:
- Switch RemovalPolicy.DESTROY → RemovalPolicy.RETAIN
- Enable bucket versioning (versioned=True) for rollback support
- Add server-side encryption (encryption=s3.BucketEncryption.S3_MANAGED)
"""

import os

from aws_cdk import CfnOutput, RemovalPolicy
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

# Local directory that seed.py writes artifacts into.
# CDK will zip+upload this to the bootstrap asset bucket, then
# BucketDeployment will extract it into the RAG bucket under prefix "index/".
_ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "assets", "index"
)


class StorageConstruct(Construct):
    """Creates the S3 bucket and deploys the FAISS index assets at deploy time."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "KBAgentBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        # ── BucketDeployment — atomic asset sync ────────────────────────────
        # Syncs assets/index/ → s3://bucket/index/
        # CDK hashes the source directory; re-deploy only happens when content changes.
        # The BucketDeployment custom resource Lambda runs in the same account.
        if os.path.isdir(_ASSETS_DIR):
            s3deploy.BucketDeployment(
                self,
                "IndexDeployment",
                sources=[s3deploy.Source.asset(_ASSETS_DIR)],
                destination_bucket=self.bucket,
                destination_key_prefix="index",
                # Prune=True ensures stale files are removed on re-deploy
                prune=True,
                memory_limit=512,
            )
        # ── Outputs ─────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "BucketName",
            value=self.bucket.bucket_name,
            description="S3 bucket for RAG FAISS index",
            export_name="KBAgent-BucketName",
        )

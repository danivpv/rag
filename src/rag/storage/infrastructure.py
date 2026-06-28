"""
StorageConstruct — S3 bucket for documents and FAISS index.

Design decisions:
- RemovalPolicy.DESTROY + auto_delete_objects so `cdk destroy` leaves a clean
  account.  auto_delete_objects deploys a CDK-managed Lambda custom resource
  that empties the bucket before CloudFormation deletes it (S3 refuses to
  delete non-empty buckets).
- enforce_ssl=True adds a bucket policy that denies HTTP-only requests
  (aws:SecureTransport == false). Not the CDK default; required by
  Well-Architected Security pillar.
- Note: the ECR repository created for the Docker Lambda image lives in the
  CDKToolkit bootstrap stack, not here. `cdk destroy` does NOT remove ECR
  images; run `aws ecr delete-repository --force` manually if needed.
"""

from aws_cdk import CfnOutput, RemovalPolicy
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageConstruct(Construct):
    """Creates and owns the S3 bucket used by the RAG engine."""

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

        # ── Outputs ─────────────────────────────────────────────────────────
        # Export the physical bucket name so scripts/seed.py can read it:
        #   aws cloudformation describe-stacks \
        #     --stack-name KBAgentStack \
        #     --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
        #     --output text
        CfnOutput(
            self,
            "BucketName",
            value=self.bucket.bucket_name,
            description="S3 bucket for RAG documents and FAISS index",
            export_name="KBAgent-BucketName",
        )

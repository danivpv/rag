"""
RagComponent — CDK Construct that wires the stateless RAG subsystems.

This component intentionally excludes StorageConstruct, which lives in a
separate stateful stack (KBAgentStorageStack) in app.py.  The separation
prevents accidental data loss if compute or API constructs are renamed:
CloudFormation logical IDs in one stack cannot affect resources in another.

Dependency order at synth time (all Python object references, not CFN exports):
    ComputeConstruct(bucket) → ApiConstruct(fn)

Exposed properties:
    .fn   — the Lambda IFunction (for adding event sources, alarms, etc.)
    .api  — the RestApi (for adding routes or custom domains in future)
"""

from aws_cdk import aws_s3 as s3
from constructs import Construct

from rag.api.infrastructure import ApiConstruct
from rag.rag.infrastructure import ComputeConstruct


class RagComponent(Construct):
    """Composite stateless construct: Compute → API."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.compute = ComputeConstruct(self, "Compute", bucket=bucket)
        self.api = ApiConstruct(self, "Api", handler=self.compute.fn)

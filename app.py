"""
CDK App entrypoint.

Invoked by cdk.json: "app": "uv run python app.py"

Two-stack design (stateful / stateless separation):
- KBAgentStorageStack: owns the S3 bucket. Termination protection ON —
  `cdk destroy` will refuse to delete this stack unless you pass --force,
  preventing accidental data loss. In production: set RemovalPolicy.RETAIN.
- KBAgentStack: owns compute (Docker Lambda) and API (API Gateway). Stateless
  — safe to redeploy, rename constructs, or destroy without data risk.

Upgrade path:
- To add Cognito: inject a CognitoConstruct into RagComponent.
"""

import aws_cdk as cdk

from constants import REGION, STACK_NAME
from rag.component import RagComponent
from rag.storage.infrastructure import StorageConstruct


class KBAgentStorageStack(cdk.Stack):
    """Stateful stack — S3 bucket. Protected from accidental deletion."""

    def __init__(self, scope: cdk.App, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.storage = StorageConstruct(self, "Storage")


class KBAgentStack(cdk.Stack):
    """Stateless stack — Docker Lambda + API Gateway."""

    def __init__(
        self,
        scope: cdk.App,
        construct_id: str,
        *,
        storage_stack: KBAgentStorageStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.rag = RagComponent(self, "Rag", bucket=storage_stack.storage.bucket)


# ── App synthesis ───────────────────────────────────────────────────────────
app = cdk.App()

env = cdk.Environment(region=REGION)
common_tags = {
    "Project": "kb-agent",
    "ManagedBy": "cdk",
}

storage_stack = KBAgentStorageStack(
    app,
    f"{STACK_NAME}Storage",
    env=env,
    description="KB Agent — stateful S3 storage (protected)",
    termination_protection=True,
    tags=common_tags,
)

KBAgentStack(
    app,
    STACK_NAME,
    env=env,
    description="KB Agent — stateless compute and API layer",
    storage_stack=storage_stack,
    tags=common_tags,
)

app.synth()

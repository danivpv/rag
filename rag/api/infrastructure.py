"""
ApiConstruct — API Gateway REST API with API Key authentication.

Design decisions:
- REST API (not HTTP API v2): REST API has native API Key + Usage Plan support.
  HTTP API v2 is ~70% cheaper per request but requires a Lambda Authorizer for
  key-based auth. Upgrade path: swap to HTTP API + Cognito JWT authorizer for
  production identity; routing and Lambda code remain unchanged.
- /health  GET  — no auth; used by smoke tests and health checks.
- /query   POST — API key required; the core RAG endpoint.
- Lambda proxy integration: the Mangum adapter in the Lambda converts the
  APIGW proxy event to ASGI, so we use a single catch-all integration.
- Usage Plan throttle: 10 RPS sustained / 20 burst prevents runaway Bedrock
  costs. Add a monthly quota (see commented block below) for spend caps.
- CloudWatch access logs enabled: captures one structured JSON line per APIGW
  request *before* it reaches Lambda — distinct from Lambda execution logs.
  Required by the brief (§8: "logging resources").
- CfnOutputs for ApiUrl and ApiKeyId let scripts discover endpoints without
  any hard-coded values.

Upgrade path to Cognito:
  Replace `api_key_required=True` on /query with a CognitoUserPoolsAuthorizer.
  The Lambda integration and routing code stay unchanged.
"""

from aws_cdk import CfnOutput
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from constants import THROTTLE_BURST_LIMIT, THROTTLE_RATE_LIMIT


class ApiConstruct(Construct):
    """Creates and owns the API Gateway REST API."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        handler: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── CloudWatch access log group ─────────────────────────────────────
        # One structured JSON line per APIGW request: method, path, status,
        # latency, request ID.  Retention set to avoid unbounded CloudWatch cost.
        access_log_group = logs.LogGroup(
            self,
            "ApiAccessLogs",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ── REST API ────────────────────────────────────────────────────────
        # We pin the stage name to "prod" so the URL is predictable.
        self.api = apigw.RestApi(
            self,
            "KBAgentApi",
            description="KB Agent RAG API",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=THROTTLE_RATE_LIMIT,
                throttling_burst_limit=THROTTLE_BURST_LIMIT,
                access_log_destination=apigw.LogGroupLogDestination(access_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=False,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=False,
                ),
            ),
        )

        # ── Lambda proxy integration ────────────────────────────────────────
        # APIGW forwards the full HTTP envelope; Mangum in the Lambda converts
        # it to ASGI.  proxy=True is explicit here for reviewer clarity.
        integration = apigw.LambdaIntegration(handler, proxy=True)

        # ── /health  GET  (no auth) ─────────────────────────────────────────
        health = self.api.root.add_resource("health")
        health.add_method("GET", integration)

        # ── /query  POST  (API key required) ───────────────────────────────
        query = self.api.root.add_resource("query")
        query.add_method(
            "POST",
            integration,
            api_key_required=True,
        )

        # ── API Key + Usage Plan ────────────────────────────────────────────
        # CDK generates the key value automatically.  Retrieve the secret via:
        #   aws apigateway get-api-key --api-key <KeyId> --include-value
        key = self.api.add_api_key("KBAgentKey")

        plan = self.api.add_usage_plan(
            "KBAgentUsagePlan",
            throttle=apigw.ThrottleSettings(
                rate_limit=THROTTLE_RATE_LIMIT,
                burst_limit=THROTTLE_BURST_LIMIT,
            ),
            # quota=apigw.QuotaSettings(limit=10_000, period=apigw.Period.MONTH)
            # Uncomment above in production to cap monthly Bedrock spend.
        )
        plan.add_api_key(key)
        plan.add_api_stage(stage=self.api.deployment_stage)

        # ── Outputs ─────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            description="Base URL of the KB Agent REST API (prod stage)",
            export_name="KBAgent-ApiUrl",
        )
        CfnOutput(
            self,
            "ApiKeyId",
            value=key.key_id,
            description="API Gateway key ID — retrieve secret with: aws apigateway get-api-key --api-key <ID> --include-value",
            export_name="KBAgent-ApiKeyId",
        )

"""
scripts/test_api.py — End-to-End API Smoke Tests

Runs three smoke tests against the deployed KB Agent API:
  1. Health check (GET /health, no auth) → 200
  2. Auth rejection (POST /query, no API key) → 403
  3. Authenticated query (POST /query, valid key) → 200 + valid fields

Usage:
    uv run --group data-ingestion python scripts/test_api.py [OPTIONS]

Options:
    --profile NAME    AWS CLI profile (used to look up API key from AWS if not in .env)
    --verbose         Print full response bodies

Prerequisites:
    1. CDK stacks deployed (KBAgentStackStorage + KBAgentStack)
    2. seed.py run successfully (FAISS index in S3)
    3. .env populated (or env vars set):
         API_BASE_URL=https://<id>.execute-api.us-east-1.amazonaws.com/prod
         API_TOKEN=<your-api-gateway-key-value>

Environment Variables (.env):
    API_BASE_URL    — base URL of the deployed API (no trailing slash)
    API_TOKEN       — API Gateway key value (x-api-key header)
    AWS_PROFILE     — optional AWS profile (overrides --profile)

Design notes:
    - All request payloads are written to scripts/input/<test_name>.json FIRST
      before any HTTP call is made. This satisfies the Windows/Git Bash JSON
      escaping constraint and provides a debug artifact.
    - Payloads dir is created automatically if it doesn't exist.
    - Colored output: GREEN=pass, RED=fail, YELLOW=warn.
    - Exit code: 0 if all tests pass, 1 if any fail.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Annotated

import requests
import typer
from dotenv import load_dotenv

app = typer.Typer(help="End-to-end smoke tests for the KB Agent API.")

# ---------------------------------------------------------------------------
# ANSI colors (safe on most terminals; suppressed if not a TTY)
# ---------------------------------------------------------------------------
_TTY = sys.stdout.isatty()


def _color(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def green(t: str) -> str:
    return _color("32;1", t)


def red(t: str) -> str:
    return _color("31;1", t)


def yellow(t: str) -> str:
    return _color("33;1", t)


def cyan(t: str) -> str:
    return _color("36", t)


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------
PAYLOADS_DIR = Path(__file__).parent / "input"


def write_payload(name: str, body: dict[str, Any]) -> Path:
    """Write request payload to scripts/input/<name>.json before any HTTP call."""
    PAYLOADS_DIR.mkdir(exist_ok=True)
    path = PAYLOADS_DIR / f"{name}.json"
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
class TestResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed = False
        self.message = ""
        self.duration_ms = 0


def run_test(
    name: str,
    method: str,
    path: str,
    base_url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    expected_status: int,
    response_checks: list[tuple[str, Any]] | None = None,
    verbose: bool = False,
) -> TestResult:
    """
    Execute a single HTTP test.

    Args:
        name: Short test name (also used as payload filename)
        method: HTTP method (GET, POST)
        path: URL path (e.g., "/health")
        base_url: API base URL (no trailing slash)
        payload: Request body dict (written to input/ before call)
        headers: Additional headers
        expected_status: Expected HTTP status code
        response_checks: List of (json_key, expected_value) for response body validation
        verbose: Print full response body
    """
    result = TestResult(name)
    url = f"{base_url.rstrip('/')}{path}"
    headers = headers or {}

    # Write payload file FIRST (constraint: never pass raw JSON via bash args)
    if payload is not None:
        payload_path = write_payload(name, payload)
        headers.setdefault("Content-Type", "application/json")
        print(f"  {cyan('Payload:')} {payload_path}")

    print(f"\n{cyan('─' * 50)}")
    print(f"{cyan('TEST:')} {name}")
    print(f"  {method} {url}")
    if headers:
        safe_headers = {
            k: (v[:8] + "..." if k.lower() == "x-api-key" else v)
            for k, v in headers.items()
        }
        print(f"  Headers: {safe_headers}")

    start = time.monotonic()
    try:
        resp = requests.request(
            method,
            url,
            json=payload,
            headers=headers,
            timeout=35,  # Lambda cold start can be ~20s
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        result.duration_ms = elapsed_ms

        print(f"  Status:  {resp.status_code}  ({elapsed_ms} ms)")

        if verbose and resp.text:
            try:
                print(f"  Body:    {json.dumps(resp.json(), indent=4)}")
            except Exception:  # noqa: BLE001
                print(f"  Body:    {resp.text[:500]}")

        # Write response to output directory
        out_dir = Path(__file__).parent / "output"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{name}_response.json"
        try:
            out_path.write_text(json.dumps(resp.json(), indent=2), encoding="utf-8")
        except Exception:
            out_path.write_text(resp.text, encoding="utf-8")
        print(f"  {cyan('Output:')}  {out_path}")

        # Status check
        if resp.status_code != expected_status:
            result.message = f"Expected HTTP {expected_status}, got {resp.status_code}"
            print(f"  {red('FAIL')} — {result.message}")
            return result

        # Response field checks
        if response_checks and resp.status_code == 200:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                result.message = "Response is not valid JSON"
                print(f"  {red('FAIL')} — {result.message}")
                return result

            for key, expected in response_checks:
                if key not in body:
                    result.message = f"Missing key '{key}' in response"
                    print(f"  {red('FAIL')} — {result.message}")
                    return result
                if expected is not None and body[key] != expected:
                    result.message = (
                        f"Key '{key}': expected {expected!r}, got {body[key]!r}"
                    )
                    print(f"  {red('FAIL')} — {result.message}")
                    return result

            if not verbose:
                # Print a short summary of the response
                summary = {
                    k: v
                    for k, v in body.items()
                    if k in ("answer", "confidence", "sources")
                }
                if summary:
                    ans = str(summary.get("answer", ""))[:120]
                    conf = summary.get("confidence", "n/a")
                    n_sources = len(summary.get("sources", []))
                    print(f"  Answer:     {ans}...")
                    print(f"  Confidence: {conf}")
                    print(f"  Sources:    {n_sources} chunk(s)")

        result.passed = True
        print(f"  {green('PASS')}")

    except requests.exceptions.Timeout:
        result.message = "Request timed out after 35s"
        print(f"  {red('FAIL')} — {result.message}")
    except requests.exceptions.ConnectionError as exc:
        result.message = f"Connection error: {exc}"
        print(f"  {red('FAIL')} — {result.message}")

    return result


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------
def run_all_tests(base_url: str, api_token: str, verbose: bool) -> list[TestResult]:
    results: list[TestResult] = []

    # ── Test 1: Health check (no auth) ──────────────────────────────────────
    results.append(
        run_test(
            name="01_health",
            method="GET",
            path="/health",
            base_url=base_url,
            expected_status=200,
            response_checks=[("status", "ok")],
            verbose=verbose,
        )
    )

    # ── Test 2: Auth rejection (POST /query, no API key) ────────────────────
    results.append(
        run_test(
            name="02_auth_rejection",
            method="POST",
            path="/query",
            base_url=base_url,
            payload={"question": "What is RAG?"},
            # Deliberately no x-api-key header
            expected_status=403,
            verbose=verbose,
        )
    )

    # ── Test 3: Authenticated query ──────────────────────────────────────────
    results.append(
        run_test(
            name="03_authenticated_query",
            method="POST",
            path="/query",
            base_url=base_url,
            payload={
                "question": "What is retrieval-augmented generation and why is it useful?"
            },
            headers={"x-api-key": api_token},
            expected_status=200,
            response_checks=[
                ("answer", None),  # key must exist, any value
                ("confidence", None),  # key must exist
                ("sources", None),  # key must exist
            ],
            verbose=verbose,
        )
    )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
@app.command()
def main(
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="AWS CLI profile (used if API_TOKEN is missing from .env).",
            envvar="AWS_PROFILE",
        ),
    ] = "default",
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Print full response bodies.")
    ] = False,
) -> None:
    """Run smoke tests against the KB Agent API."""
    load_dotenv(override=False)

    # Config resolution
    base_url = os.environ.get("API_BASE_URL", "").strip().rstrip("/")
    api_token = os.environ.get("API_TOKEN", "").strip()

    missing_config: list[str] = []
    if not base_url:
        missing_config.append("API_BASE_URL")
    if not api_token:
        missing_config.append("API_TOKEN")

    if missing_config:
        print(
            red("ERROR: Missing required configuration:\n")
            + "\n".join(f"  {k}" for k in missing_config)
            + "\n\nSet these in a .env file in the project root:\n"
            "  API_BASE_URL=https://<id>.execute-api.us-east-1.amazonaws.com/prod\n"
            "  API_TOKEN=<your-api-gateway-key-value>\n\n"
            "Retrieve the API key value with:\n"
            "  aws apigateway get-api-keys --include-values --query 'items[0].value' "
            "--output text --profile <profile>",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)

    print(f"\n{cyan('KB Agent — API Smoke Tests')}")
    print(f"  Base URL: {base_url}")
    print(f"  API key:  {api_token[:8]}...")
    print(f"  Profile:  {profile}")
    print(f"  Payloads: {PAYLOADS_DIR}")

    results = run_all_tests(base_url, api_token, verbose=verbose)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{cyan('=' * 50)}")
    print(f"{cyan('SUMMARY')}")
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    for r in results:
        status = green("PASS") if r.passed else red("FAIL")
        msg = f"  — {r.message}" if not r.passed else f"  ({r.duration_ms} ms)"
        print(f"  [{status}] {r.name}{msg}")

    print(f"\n  {passed}/{total} tests passed")
    print(cyan("=" * 50))

    if passed != total:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

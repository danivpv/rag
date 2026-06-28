"""
FastAPI application + Mangum Lambda handler.

Entry point for both:
  - Lambda (via Mangum ASGI adapter, CMD ["main.handler"])
  - Local dev (uvicorn main:app --reload)

lifespan="off" disables Starlette's async lifespan events — not needed here
because we initialise Bedrock/FAISS lazily on first request (warm start cache).
"""

from fastapi import FastAPI
from mangum import Mangum

from .api.routes import router

app = FastAPI(
    title="KB Agent API",
    version="1.0.0",
    description=(
        "Knowledge-Base RAG API — query documents stored in S3, "
        "retrieved via FAISS, answered by Amazon Bedrock Claude Haiku."
    ),
    docs_url=None,
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.include_router(router)

# Mangum translates API Gateway Lambda proxy events → ASGI.
# lifespan="off": no async startup/shutdown hooks needed; FAISS is loaded lazily.
handler = Mangum(app, lifespan="off")

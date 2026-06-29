# ==============================================================================
# STAGE 1: THE BUILDER (Identical for Lambda and ECS)
# ==============================================================================
# For Lambda, we use the Lambda base. For pure ECS, you would switch this to python:3.12-slim
FROM public.ecr.aws/lambda/python:3.12-x86_64 AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_PROGRESS=1
ENV UV_LINK_MODE=copy

WORKDIR /build

# Cache Layer 1: Third-Party Dependencies Only
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# Cache Layer 2: Project Code & Installation
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


# ==============================================================================
# STAGE 2: FINAL RUNTIME (Configured for AWS Lambda)
# ==============================================================================
FROM public.ecr.aws/lambda/python:3.12-x86_64

# Lambda demands a flat layout: copy everything straight into the task root
COPY --from=builder /build/.venv/lib/python3.12/site-packages ${LAMBDA_TASK_ROOT}/

# Use the natively installed package from site-packages
CMD ["rag.rag.runtime.main.handler"]


# ==============================================================================
# MIGRATION BLUEPRINT: HOW TO SHIFT THIS TO AWS ECS (or Docker/Kubernetes)
# ==============================================================================
# To migrate this Dockerfile to a standard web service layout for ECS, 
# you only need to swap out Stage 2 with the following 4 structural steps:
#
# STEP 1: Change the Base Images
#   - Replace both `public.ecr.aws/lambda/python:3.12-x86_64` images with 
#     a standard lightweight image: `python:3.12-slim`.
#
# STEP 2: Retain the Virtual Environment (Do not flatten it)
#   - Instead of pulling out the site-packages, copy the entire `.venv` folder intact.
#   - Replace the Lambda COPY command with:
#     `COPY --from=builder /build/.venv /app/.venv`
#     `COPY . /app`
#     `WORKDIR /app`
#
# STEP 3: Environment Activation via PATH
#   - Standard containers respect virtual environments natively if they are on the PATH.
#   - Add this environment variable to make your venv active by default:
#     `ENV PATH="/app/.venv/bin:$PATH"`
#
# STEP 4: Process Execution
#   - Swap the Lambda handler CMD for a long-running web server process:
#     `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]`
# ==============================================================================

FROM public.ecr.aws/lambda/python:3.12-x86_64

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY . ${LAMBDA_TASK_ROOT}/

# Lambda entrypoint
CMD ["main.handler"]

# To run on ECS Fargate, comment the CMD above and uncomment this ENTRYPOINT:
# ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]

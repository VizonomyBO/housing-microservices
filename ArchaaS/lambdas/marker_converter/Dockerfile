# Lightweight Lambda for document conversion using markitdown
FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly set the handler so the Lambda entrypoint always finds it
ENV _HANDLER=handler.handler
ENV AWS_LAMBDA_FUNCTION_HANDLER=handler.handler

# Copy handler
COPY handler.py .
COPY core/ ./core/

CMD ["handler.handler"]

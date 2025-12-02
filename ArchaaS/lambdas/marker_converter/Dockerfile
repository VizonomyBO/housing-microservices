# Lightweight Lambda for document conversion using markitdown
FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy handler
COPY handler.py .
COPY core/ ./core/

CMD ["handler.handler"]

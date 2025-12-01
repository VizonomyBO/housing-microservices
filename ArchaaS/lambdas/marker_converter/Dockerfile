# Container-based Lambda for Marker PDF converter
# Uses AWS Lambda Python 3.12 base image

FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for Marker (PDF processing)
# Note: Marker uses its own OCR models, tesseract not required
RUN dnf install -y \
    poppler-utils \
    && dnf clean all

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
# Note: Marker is heavy, consider using a smaller model or pre-caching
RUN pip install --no-cache-dir -r requirements.txt

# Models will be downloaded at runtime on first invocation
# This keeps image size small but first cold start will be slow (~2-3 min)

# Copy application code
COPY handler.py .
COPY core/ ./core/

# Set the handler
CMD ["handler.handler"]


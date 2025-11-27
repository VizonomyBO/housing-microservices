# Container-based Lambda for Marker PDF converter
# Uses AWS Lambda Python 3.12 base image

FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for Marker (OCR, PDF processing)
RUN dnf install -y \
    poppler-utils \
    tesseract \
    tesseract-langpack-eng \
    && dnf clean all

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
# Note: Marker is heavy, consider using a smaller model or pre-caching
RUN pip install --no-cache-dir -r requirements.txt

# Download Marker models during build (optional - can also download at runtime)
# This makes cold starts faster but increases image size
RUN python -c "from marker.models import create_model_dict; create_model_dict()" || true

# Copy application code
COPY handler.py .
COPY core/ ./core/

# Set the handler
CMD ["handler.handler"]


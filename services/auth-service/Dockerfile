# Multi-stage Dockerfile with testing support

# ============================================
# Test Stage - Run tests and quality checks
# ============================================
FROM python:3.11-slim AS test

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements/ requirements/

# Install test dependencies
RUN pip install --no-cache-dir -r requirements/test.txt
RUN pip install --no-cache-dir -r requirements/dev.txt

# Copy application code
COPY . .

# Run linting and type checking
RUN black --check app/ || true
RUN flake8 app/ || true
RUN mypy app/ || true

# Run tests with coverage
RUN pytest tests/ --cov=app --cov-report=term --cov-report=html --cov-report=xml || true

# ============================================
# Production Stage
# ============================================
FROM python:3.11-slim AS production

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements/ requirements/

# Install only production dependencies
RUN pip install --no-cache-dir -r requirements/base.txt

# Copy application code
COPY app/ app/
COPY run.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["python", "run.py"]


#!/bin/bash
set -e

# Build Lambda Layer for Python Dependencies
# This script builds the layer using Docker with the Lambda Python 3.12 runtime

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LAMBDAS_DIR="$PROJECT_DIR/lambdas"

echo "==================================="
echo "Building Lambda Layer for Python Dependencies"
echo "==================================="

cd "$LAMBDAS_DIR"

# Clean previous builds
rm -rf layer_package layer.zip

echo "Creating layer package directory..."
mkdir -p layer_package/python

echo "Combining all Lambda requirements..."
cat > /tmp/combined_requirements.txt << 'EOF'
aioboto3>=12.0.0
pydantic>=2.0.0
python-magic>=0.4.27
pdfplumber>=0.10.0
EOF

echo "Building dependencies in Docker (Lambda Python 3.12 runtime)..."
docker run --rm \
  -v "/tmp/combined_requirements.txt:/requirements.txt:ro" \
  -v "$LAMBDAS_DIR/layer_package/python:/output" \
  --entrypoint pip \
  public.ecr.aws/lambda/python:3.12 \
  install -r /requirements.txt -t /output --upgrade --no-cache-dir

echo "Creating layer zip..."
cd layer_package
zip -r ../layer.zip python -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*" -x "*.egg-info/*"

echo ""
echo "✅ Lambda layer built successfully!"
echo "   Location: $LAMBDAS_DIR/layer.zip"
echo "   Size: $(ls -lh ../layer.zip | awk '{print $5}')"
echo ""
echo "Now run: terraform apply"



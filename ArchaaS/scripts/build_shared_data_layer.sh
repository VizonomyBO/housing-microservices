#!/bin/bash
# Build Lambda layer containing shared_data_layer package and dependencies
# This layer provides database access for all ingestion Lambdas

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/../lambdas"
LAYER_DIR="$OUTPUT_DIR/shared_layer_package"

echo "=== Building shared_data_layer Lambda Layer ==="
echo "Project root: $PROJECT_ROOT"
echo "Output directory: $OUTPUT_DIR"

# Clean previous build
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR/python"

# Create a temporary requirements file for Lambda layer
cat > "$LAYER_DIR/requirements.txt" << 'EOF'
# Core database dependencies
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.30.0
pydantic>=2.7.0
pydantic-settings>=2.0.0
pgvector>=0.2.0

# For MIME type detection
python-magic>=0.4.27

# AWS SDK (for EventBridge events)
boto3>=1.34.0

# Alembic is not needed at runtime for Lambdas
EOF

echo "Installing dependencies for manylinux2014_x86_64..."
python3 -m pip install \
    --platform manylinux2014_x86_64 \
    --target "$LAYER_DIR/python" \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    -r "$LAYER_DIR/requirements.txt"

# Copy shared_data_layer source code
echo "Copying shared_data_layer package..."
cp -r "$PROJECT_ROOT/packages/shared_data_layer/src/shared_data_layer" "$LAYER_DIR/python/"

# Remove unnecessary files to reduce layer size
echo "Cleaning up unnecessary files..."
find "$LAYER_DIR/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$LAYER_DIR/python" -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove testing module from shared_data_layer (not needed in Lambda)
rm -rf "$LAYER_DIR/python/shared_data_layer/testing" 2>/dev/null || true
rm -rf "$LAYER_DIR/python/shared_data_layer/migrations" 2>/dev/null || true

# Create the zip file
echo "Creating layer zip..."
cd "$LAYER_DIR"
zip -r "$OUTPUT_DIR/shared_layer.zip" python -x "*.pyc" -x "*__pycache__*"

# Show layer size
LAYER_SIZE=$(du -sh "$OUTPUT_DIR/shared_layer.zip" | cut -f1)
echo ""
echo "=== Build Complete ==="
echo "Layer file: $OUTPUT_DIR/shared_layer.zip"
echo "Layer size: $LAYER_SIZE"

# Clean up
rm -rf "$LAYER_DIR"
rm -f "$LAYER_DIR/requirements.txt"

echo "Done!"


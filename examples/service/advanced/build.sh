#!/bin/bash
# Build script for advanced example
# This file is automatically included in the package when buildcmd is specified

set -e

echo "=== Advanced Example Build ==="
echo "Build timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "Installing dependencies..."
pip install -r requirements.txt -t .

echo "Build complete!"

#!/bin/bash
# Quick test runner script for DCA system

echo "Running DCA Test Suite..."
echo "========================================"

cd /Users/diverse/Downloads/pliro

# Set Python path
export PYTHONPATH=/Users/diverse/Downloads/pliro

# Activate venv
source .venv/bin/activate

# Run all DCA tests with verbosity
pytest tests/test_dca_*.py -v --tb=short

echo ""
echo "Test run completed!"

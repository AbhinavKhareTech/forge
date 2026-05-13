#!/bin/bash
set -e

# Local Development Setup Script

echo "Setting up Forge for local development..."

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -e ".[dev]"

# Install pre-commit hooks
if command -v pre-commit >/dev/null 2>&1; then
    echo "Installing pre-commit hooks..."
    pre-commit install
fi

# Create local directories
mkdir -p specs constitutions .forge/graph logs

# Run tests
echo "Running tests..."
pytest -v

echo ""
echo "Setup complete! Activate the environment with:"
echo "  source .venv/bin/activate"
echo ""
echo "Run Forge with:"
echo "  forge init my-project"
echo "  forge spec validate specs/sample.md"
echo "  forge run SPEC-001"

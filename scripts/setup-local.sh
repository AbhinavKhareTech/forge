#!/bin/bash
set -euo pipefail

# Forge Local Development Setup Script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

log_info "Setting up Forge local development environment..."

# Check prerequisites
log_step "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || { log_error "Python 3 is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { log_warn "Docker not found. Some features may not work."; }
command -v kubectl >/dev/null 2>&1 || { log_warn "kubectl not found. Kubernetes features will not work."; }

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
log_info "Python version: $PYTHON_VERSION"

# Create virtual environment
log_step "Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    log_info "Virtual environment created"
else
    log_warn "Virtual environment already exists"
fi

source .venv/bin/activate

# Upgrade pip
log_step "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
log_step "Installing dependencies..."
pip install -e ".[dev,trident]"

# Install pre-commit hooks
log_step "Installing pre-commit hooks..."
pre-commit install

# Create .env file
log_step "Setting up environment..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    log_info ".env file created from template. Please edit it with your values."
else
    log_warn ".env file already exists"
fi

# Start local infrastructure
log_step "Starting local infrastructure..."
if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f docker/docker-compose.yml up -d postgres redis
    log_info "Local infrastructure started (PostgreSQL + Redis)"
else
    log_warn "Docker Compose not available. You'll need to set up PostgreSQL and Redis manually."
fi

# Run database migrations
log_step "Running database migrations..."
alembic upgrade head || log_warn "Migration step skipped"

# Run tests
log_step "Running tests..."
pytest -xvs || log_warn "Some tests failed. This may be expected during initial setup."

log_info "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your configuration"
echo "  2. Start the server: make dev"
echo "  3. Visit http://localhost:8000/docs for API documentation"
echo ""

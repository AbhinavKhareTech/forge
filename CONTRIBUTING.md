# Contributing to Forge

Thank you for your interest in contributing to Forge! This document provides guidelines and workflows for contributing.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/ahinsaai/forge.git
cd forge

# Install development dependencies
make install

# Run pre-commit hooks
pre-commit install
pre-commit run --all-files
```

## Development Workflow

1. **Fork and Branch**: Create a feature branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Code Standards**: All code must pass:
   - `ruff check` (linting)
   - `ruff format` (formatting)
   - `mypy` (type checking, strict mode)
   - `bandit` (security scan)
   - 90%+ test coverage

3. **Testing**: Write tests for all new functionality
   ```bash
   make test                    # Unit tests
   make test-integration        # Integration tests
   make test-security           # Security scans
   ```

4. **Documentation**: Update relevant docs in `docs/` and README if needed

5. **Commit Messages**: Use [Conventional Commits](https://www.conventionalcommits.org/)
   ```
   feat: add voice-driven spec generation
   fix: resolve race condition in orchestrator
   docs: update API reference
   security: harden JWT token validation
   ```

## Pull Request Process

1. Ensure all CI checks pass
2. Request review from at least 2 maintainers
3. Address review feedback
4. Squash commits if requested
5. Merge will be performed by maintainers

## Security

If you discover a security vulnerability, please email `security@ahinsa.ai` instead of opening a public issue.

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

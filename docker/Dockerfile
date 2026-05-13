# ── Stage 1: Builder ──────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Security: Run as non-root even during build
RUN groupadd -r forge && useradd -r -g forge forge

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     gcc     libpq-dev     && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY pyproject.toml README.md ./
COPY src/forge/__version__.py src/forge/__version__.py

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip &&     pip install --no-cache-dir hatchling &&     pip install --no-cache-dir -e ".[trident]"

# ── Stage 2: Production ───────────────────────────────────────
FROM python:3.12-slim-bookworm AS production

LABEL org.opencontainers.image.title="Forge"
LABEL org.opencontainers.image.description="Agent-Native SDLC Control Plane"
LABEL org.opencontainers.image.source="https://github.com/ahinsaai/forge"
LABEL org.opencontainers.image.licenses="MIT"

# Security: Minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     libpq5     curl     && rm -rf /var/lib/apt/lists/*     && apt-get clean

# Security: Create non-root user
RUN groupadd -r forge && useradd -r -g forge -d /app forge

WORKDIR /app

# Copy only necessary artifacts from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/forge /usr/local/bin/forge
COPY src/ ./src/

# Security: Set proper ownership
RUN chown -R forge:forge /app

# Security: Switch to non-root user
USER forge

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD curl -f http://localhost:8000/health/live || exit 1

# Expose ports
EXPOSE 8000 9090

# Environment
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONFAULTHANDLER=1     FORGE_ENVIRONMENT=production     PATH="/usr/local/bin:${PATH}"

ENTRYPOINT ["forge"]
CMD ["serve"]

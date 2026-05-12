# Forge -- Agent-Native SDLC Control Plane
# Multi-stage build for production

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     gcc     libpq-dev     && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip     && pip install --no-cache-dir hatchling

# Copy source and install
COPY src/ src/
COPY README.md .
COPY LICENSE .
RUN pip install --no-cache-dir -e ".[dev]"

# Stage 2: Production
FROM python:3.12-slim AS production

LABEL maintainer="Abhinav Khare <abhinav@ahinsa.ai>"
LABEL org.opencontainers.image.title="Forge"
LABEL org.opencontainers.image.description="Agent-Native SDLC Control Plane"
LABEL org.opencontainers.image.source="https://github.com/ahinsaai/forge"

WORKDIR /app

# Create non-root user
RUN groupadd -r forge && useradd -r -g forge forge

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends     libpq5     redis-tools     curl     && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/forge /usr/local/bin/forge

# Copy application code
COPY --chown=forge:forge src/ src/
COPY --chown=forge:forge README.md .
COPY --chown=forge:forge LICENSE .

# Create directories
RUN mkdir -p /app/specs /app/constitutions /app/.forge/graph /app/logs     && chown -R forge:forge /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD forge --version || exit 1

USER forge

ENV FORGE_ENV=production
ENV FORGE_LOG_LEVEL=info
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

ENTRYPOINT ["forge"]
CMD ["--help"]
